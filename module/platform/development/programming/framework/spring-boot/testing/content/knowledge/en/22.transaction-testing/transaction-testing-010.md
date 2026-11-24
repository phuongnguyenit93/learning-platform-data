# Testing After-Commit Events and Tasks That Must Only Run After Commit

## 1. Context, Goals, and Scope

In Spring Boot, business workflows frequently write data to the database and only then send notifications, record audits, evict caches, enqueue jobs, or publish domain events. Risk arises if external work executes **before the transaction commits successfully**: the transaction may roll back while the customer already received a confirmation email for an order that does not exist.

Spring Framework provides `@TransactionalEventListener` to bind event handling to the transaction lifecycle. The `TransactionPhase.AFTER_COMMIT` phase allows processing an event **after the database transaction has committed successfully**. However, this mechanism by itself does not persist events durably: the application can still crash after commit and before sending the notification. Therefore, the lesson separates:

- **Right timing**: listeners must not run on rollback and must not run before commit.
- **Right data**: tasks receive the event/ID and read committed state.
- **Right follow-up transaction**: database writes inside after-commit handlers require a new transaction when appropriate.
- **Right reliability**: retries, idempotency, and a durable outbox when losing or duplicating events is unacceptable.
- **Right testing**: `@DataJpaTest` default rollback does not automatically exercise the after-commit happy path.

You will learn how to use `@TransactionalEventListener(AFTER_COMMIT)`, `@Commit`, `@Rollback(false)`, `TestTransaction`, `@BeforeTransaction`/`@AfterTransaction`, and `@SpringBootTest` to verify these cases. The lesson includes a Java 17 Maven project with Spring Boot 3.5.16, Spring Data JPA, H2, JUnit Jupiter, and test classes showing commit/rollback timelines explicitly.

**Core point:** `save()` or `saveAndFlush()` succeeding does not mean the transaction committed. Tests must verify at a point **after an actual commit** or prove that side effects do not occur on rollback.

## 2. Mechanism of @TransactionalEventListener

### 2.1. When Is the Event Published?

A service can publish a domain event while still inside a transaction:

~~~java
@Service
class CheckoutService {
    private final ApplicationEventPublisher publisher;

    @Transactional
    public void placeOrder(String id) {
        // repository.save(...)
        publisher.publishEvent(new OrderPlaced(id));
    }
}
~~~

This is an illustrative snippet, not a standalone compilable Java file. `publishEvent` passes the event to event infrastructure. A regular listener annotated with `@EventListener` can run immediately upon publication; `@TransactionalEventListener` registers a synchronization callback tied to the current transaction's phase.

Simple diagram:

~~~text
service @Transactional
  |
  +-- begin T1
  +-- INSERT business row
  +-- publishEvent(OrderPlaced)
  |     |
  |     +-- @TransactionalEventListener registers synchronization
  |
  +-- BEFORE_COMMIT callbacks
  +-- database COMMIT T1
  +-- AFTER_COMMIT callbacks
  +-- AFTER_COMPLETION callbacks
  +-- clean up transaction resources
  |
  +-- service caller continues
~~~

The sequence shows **lifecycle semantics**. Details of callbacks/interceptors and exact timing of resource release can vary by transaction manager. Do not use it to claim all listener types, executors, or remote side effects complete at the exact same instant.

### 2.2. Four Phases to Remember

| Phase | Condition | Meaning in tests |
| --- | --- | --- |
| `BEFORE_COMMIT` | Transaction is about to commit | Not yet safe to conclude the transaction succeeded |
| `AFTER_COMMIT` | Transaction committed successfully | Safe to start post-commit work |
| `AFTER_ROLLBACK` | Transaction rolled back | Proves success tasks were not triggered |
| `AFTER_COMPLETION` | Transaction completed, commit or rollback | Cleanup/metrics for both paths |

`AFTER_COMMIT` is the **default** phase of `@TransactionalEventListener`. Write `phase = TransactionPhase.AFTER_COMMIT` explicitly when business requirements should read clearly.

### 2.3. How Does @EventListener Differ?

~~~java
@EventListener
void immediate(OrderPlaced event) {
    // Standard handler; does not automatically wait for transaction commit.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void committed(OrderPlaced event) {
    // Phase-bound handler, only after successful commit.
}
~~~

Both are descriptive snippets. If the application configures a custom event multicaster or `@Async`, callback timing can differ. Tests must reflect the actual configuration rather than assuming all listeners are invoked synchronously in every scenario.

### 2.4. No Active Transaction?

Per Spring Framework 6.2, `@TransactionalEventListener` defaults to `fallbackExecution = false`. When publishing an event **outside a transaction**, the listener does not handle the event because there is no commit boundary to bind to.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false)
void afterCommit(OrderPlaced event) {
    // Not invoked when published outside a transaction.
}
~~~

If business logic needs the event handled even without a transaction, you can use `fallbackExecution = true`. In that case, tests must distinguish **fallback without a transaction** from **`AFTER_COMMIT` with a transaction**; never treat fallback execution as a successful commit.

### 2.5. Imperative vs. Reactive Transactions

This lesson uses Spring Data JPA and `PlatformTransactionManager`: transaction context is thread-bound, typically via `ThreadLocal`. Spring Framework 6.1+ also supports reactive transaction events with `ReactiveTransactionManager`, yet transaction context lives in the Reactor Context; you must use an appropriate transaction-context-aware publisher such as `TransactionalEventPublisher`. Never apply JPA `TestTransaction` directly to reactive publishers.

## 3. Why Can Default Tests Mislead You?

### 3.1. @DataJpaTest Rolls Back After the Test

`@DataJpaTest` in Spring Boot 3.5 configures transactional tests with **default rollback**. A `@Transactional(propagation = REQUIRED)` service called through a Spring proxy usually joins the outer test-managed transaction instead of opening an independent transaction.

~~~text
Spring TestContext opens T1
  |
  +-- test calls service.placeOrder()
  |    +-- repository.saveAndFlush(...)
  |    +-- publisher.publishEvent(...)
  |
  +-- assert repository.findById -> data exists in T1
  +-- assert AFTER_COMMIT listener -> has not run yet
  |
  +-- TestContext rolls back T1
       +-- AFTER_COMMIT does not run
       +-- AFTER_ROLLBACK runs (if registered)
~~~

A test querying and seeing the entity inside T1 does not prove the entity committed. Thus a `@DataJpaTest` that only asserts repository state can pass green while missing email/audit/outbox tasks that must run after commit.

### 3.2. flush Differs from commit

- `repository.save(entity)` updates the JPA persistence context; SQL may run earlier or later depending on ID generation/flushing.
- `repository.flush()` sends pending SQL changes to the database **without ending the transaction**.
- `saveAndFlush(entity)` saves then flushes; it can immediately expose constraint violations.
- `commit` completes the transaction and triggers post-commit mechanisms.
- `rollback` discards DB changes belonging to that transaction; external side effects that already ran do not disappear automatically.

Some deferred constraints in PostgreSQL can raise errors **only at commit**, not at flush. If your requirements demand verifying those cases, use a real database/Testcontainers and assert around commit; the H2 demo does not substitute.

### 3.3. @SpringBootTest Does Not Auto-Roll Back

`@SpringBootTest` loads the application context, yet **does not automatically put `@Transactional` on test methods**. Without an outer test transaction, a `@Transactional(REQUIRED)` service normally opens and commits its own transaction when the method finishes. Synchronous `AFTER_COMMIT` callbacks can be checked right after the service returns.

Conversely, adding `@Transactional` on a `@SpringBootTest` test creates a test-managed transaction that typically rolls back at the end of the test. Pick the test style to match your goal rather than assuming "integration tests always auto-roll back."

### 3.4. Where Does the JUnit Lifecycle Sit?

In a Spring transactional test:
- `@BeforeEach` and `@AfterEach` normally run **inside** the test-managed transaction.
- `@BeforeTransaction` runs **before** opening T1.
- `@AfterTransaction` runs **after** T1 has completed.
- `@Commit`/`@Rollback(false)` alter T1's final outcome; commit occurs **after** the test body.
- `TestTransaction.flagForCommit()` + `TestTransaction.end()` can commit T1 **mid-test**.

Therefore, asserting "listener ran" inside `@AfterEach` of a `@Commit` test can still be too early. Use `@AfterTransaction` or `TestTransaction.end()`.

## 4. Strategies for Testing AFTER_COMMIT

### 4.1. Full Context, Without Outer Test Transaction

~~~java
@SpringBootTest
class CheckoutIntegrationTest {
    @Autowired CheckoutService checkout;

    @Test
    void committed() {
        checkout.place("purchase-1");
        // If listener is synchronous, inspect outcome after method returns.
    }
}
~~~

This snippet needs real services; the complete project appears in section 6. Without test-level `@Transactional`, the service manages its own transaction. Tests must clean up committed data.

### 4.2. @DataJpaTest + @Commit + @AfterTransaction

~~~java
@DataJpaTest
class CommitTest {
    @Test
    @Commit
    void creates() {
        // Write data and publish event inside test transaction.
    }

    @AfterTransaction
    void verifies() {
        // T1 has ended; can verify callbacks and committed rows.
    }
}
~~~

If the class needs regular `@Component` services/listeners, add selective `@Import(...)`: `@DataJpaTest` does not scan the entire business service graph automatically. After a commit test, saved data **is not automatically deleted**; cleanup must run in a separate transaction, usually inside `@AfterTransaction`/`finally`.

### 4.3. @Rollback(false) Instead of @Commit

`@Rollback(false)` serves the same purpose of changing default rollback to commit for the test-managed transaction. Use `@Commit` when you want intent clear; avoid putting both annotations on the same method unnecessarily. With class-level `@Commit`, you can override at the method level using `@Rollback`.

### 4.4. TestTransaction.commit Mid-Method

~~~java
checkout.place("purchase-2");
TestTransaction.flagForCommit();
TestTransaction.end();

// Assert committed row and listener, then clean up.
~~~

`TestTransaction` works only while a test-managed transaction is active. If you want to open T2 after committing T1, call `TestTransaction.start()` and inspect data in the fresh transaction; note that T2 may roll back while rows committed by T1 remain and still require cleanup.

### 4.5. Matrix

| Test setup | When does commit happen? | Appropriate assertion point | Data cleanup |
| --- | --- | --- | --- |
| `@SpringBootTest` without `@Transactional` | When service ends its transaction | After service return if callback is synchronous | Required |
| `@DataJpaTest` default | Rolls back at end of test | Verify `AFTER_COMMIT` did not run | T1 data rolls back automatically |
| `@DataJpaTest + @Commit` | After test body and JUnit after callbacks | `@AfterTransaction` | Required |
| `@DataJpaTest + @Rollback(false)` | Same as `@Commit` | `@AfterTransaction` | Required |
| `@DataJpaTest + TestTransaction.end()` | Immediately on `end` with commit flag | Right after `end` | Required |
| `@SpringBootTest(RANDOM_PORT)` | On server thread per service transaction | Based on HTTP result/async outcome | Do not rely on test rollback |

## 5. Designing Post-Commit Tasks with Proper Transaction Boundaries

### 5.1. Events Should Carry Minimal Data

~~~java
public record PurchasePlaced(String purchaseId) {}
~~~

Avoid passing entire lazy-loading JPA entities into events. When the listener runs after commit, the `EntityManager`/transaction lifecycle may have changed; accessing lazy associations is error-prone. Pass immutable IDs and minimal data, re-querying in a new transaction when needed.

### 5.2. Synchronous Post-Commit Listener

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void send(PurchasePlaced event) {
    notificationGateway.send(event.purchaseId());
}
~~~

This is an illustrative snippet; there is no `notificationGateway` in the practice project. Tests can use a fake gateway, asserting **not sent on rollback** and **sent after commit**. Still, the callback running does not guarantee the provider actually delivered over the network.

### 5.3. Writing to the DB After Commit: Be Careful

Spring Framework Javadoc notes that the transaction has completed, yet resources may still be bound to the thread during post-commit callbacks. If the listener calls a repository write with `REQUIRED` propagation, the operation may join the old resource and **never commit again**.

Common solution:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(PurchasePlaced event) {
        auditRepository.save(new AuditEntry(event.purchaseId(), "DONE"));
    }
}

@Component
class CommitListener {
    private final AuditWriter auditWriter;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onPlaced(PurchasePlaced event) {
        auditWriter.writeAudit(event);
    }
}
~~~

These are architectural snippets (missing constructors). Place `AuditWriter` in a **separate Spring bean** so the call goes through an AOP proxy. Putting `@Transactional(REQUIRES_NEW)` on a private method and calling `this.writeAudit(...)` in the same class normally does not open a new transaction via proxy.

### 5.4. REQUIRES_NEW Has Costs Too

It can require an extra connection while the outer transaction still holds resources, increasing pool pressure. With many concurrent callbacks, account for pool size, wait times, deadlocks, and retries. If the audit must be strictly atomic with the order, **write the audit or outbox row inside the original transaction**, rather than relying solely on a post-commit write.

### 5.5. Do Not Use BEFORE_COMMIT for Irreversible Tasks

`BEFORE_COMMIT` executes before the database confirms commit; commit can still fail. Sending emails, capturing payments, or publishing broker messages in this phase can create side effects even if T1 rolls back. Use `AFTER_COMMIT` or a durable outbox depending on reliability needs.

## 6. Designing the Runnable Project

The project demonstrates both callbacks and new transactions via:
- `PurchaseRecord`: business data in table `purchase_records`.
- `PurchasePlaced`: domain event.
- `CheckoutService`: saves purchase and publishes event inside `@Transactional`.
- `LifecycleLog`: in-memory probe recording `BEFORE_COMMIT`/`AFTER_COMMIT`/`AFTER_ROLLBACK`.
- `AuditWriter`: writes `AuditEntry` in `REQUIRES_NEW`.
- `CommitListener`: phase-bound handlers.
- Four JUnit test classes: full-context commit/rollback/no-tx; slice default rollback; slice explicit `@Commit`; slice `TestTransaction` mid-test commit.

The demo uses no SMTP, Kafka, or external services. Probes and the audit table keep assertions deterministic; production reliability is analyzed in later sections.

### 6.1. Directory Structure

~~~text
after-commit-event-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/aftercommit/
│   ├── AfterCommitApplication.java
│   ├── PurchaseRecord.java
│   ├── PurchaseRepository.java
│   ├── AuditEntry.java
│   ├── AuditEntryRepository.java
│   ├── PurchasePlaced.java
│   ├── CheckoutService.java
│   ├── LifecycleLog.java
│   ├── AuditWriter.java
│   └── CommitListener.java
└── src/test/java/com/example/aftercommit/
    ├── RealCommitLifecycleTest.java
    ├── DefaultRollbackSliceTest.java
    ├── ExplicitCommitSliceTest.java
    └── ManualCommitSliceTest.java
~~~

All classes use package `com.example.aftercommit`. JUnit test classes end with `Test` so Maven Surefire detects them automatically.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>after-commit-event-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot parent/BOM manages Spring Framework, Hibernate, JUnit, and AssertJ versions. Never pin individual Spring transaction modules that could mismatch versions.

### 6.3. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:after_commit_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 and `ddl-auto=create-drop` are solely for lab/testing. Tests using `@DataJpaTest` may have their datasource replaced with a dedicated embedded database by auto-configuration; that is normal slice behavior.

### 6.4. AfterCommitApplication.java

~~~java
package com.example.aftercommit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AfterCommitApplication {
    public static void main(String[] args) {
        SpringApplication.run(AfterCommitApplication.class, args);
    }
}
~~~

### 6.5. PurchaseRecord.java

~~~java
package com.example.aftercommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @Column(name = "purchase_id", length = 80)
    private String id;

    @Column(nullable = false, length = 32)
    private String state;

    protected PurchaseRecord() {}

    public PurchaseRecord(String id, String state) {
        this.id = id;
        this.state = state;
    }

    public String getId() {
        return id;
    }

    public String getState() {
        return state;
    }
}
~~~

IDs are supplied by tests so assertions have deterministic values. Production can use UUIDs/idempotency keys, while validating inputs and never relying on hardcoded IDs shared across tenants.

### 6.6. PurchaseRepository.java

~~~java
package com.example.aftercommit;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<PurchaseRecord, String> {
}
~~~

### 6.7. AuditEntry.java

~~~java
package com.example.aftercommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_entries")
public class AuditEntry {

    @Id
    @Column(name = "purchase_id", length = 80)
    private String id;

    @Column(nullable = false, length = 32)
    private String action;

    protected AuditEntry() {}

    public AuditEntry(String id, String action) {
        this.id = id;
        this.action = action;
    }

    public String getId() {
        return id;
    }

    public String getAction() {
        return action;
    }
}
~~~

Using purchase ID as the primary key keeps duplicate rows out of the lab. Production audits should have their own event IDs and typically store multiple records with unique idempotency keys rather than overwriting by purchase ID.

### 6.8. AuditEntryRepository.java

~~~java
package com.example.aftercommit;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditEntryRepository
        extends JpaRepository<AuditEntry, String> {
}
~~~

### 6.9. PurchasePlaced.java

~~~java
package com.example.aftercommit;

public record PurchasePlaced(String purchaseId) {}
~~~

Immutable record carrying only the ID, free of lazy JPA entities or personal information.

### 6.10. CheckoutService.java

~~~java
package com.example.aftercommit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            PurchaseRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void place(String id) {
        saveAndPublish(id);
    }

    @Transactional
    public void placeAndFail(String id) {
        saveAndPublish(id);
        throw new IllegalStateException("simulated failure");
    }

    private void saveAndPublish(String id) {
        repository.saveAndFlush(new PurchaseRecord(id, "PLACED"));
        events.publishEvent(new PurchasePlaced(id));
    }
}
~~~

Public methods `place` and `placeAndFail` are invoked through the Spring bean proxy. Private helper `saveAndPublish` has no independent transaction annotation, so self-invocation is not relied upon to open transactions. `placeAndFail` throws a `RuntimeException` **before commit**, so Spring rolls back and `AFTER_ROLLBACK` callbacks can run; `AFTER_COMMIT` does not run.

### 6.11. LifecycleLog.java

~~~java
package com.example.aftercommit;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import org.springframework.stereotype.Component;

@Component
public class LifecycleLog {

    private final ConcurrentLinkedQueue<String> before =
            new ConcurrentLinkedQueue<>();

    private final ConcurrentLinkedQueue<String> committed =
            new ConcurrentLinkedQueue<>();

    private final ConcurrentLinkedQueue<String> rolledBack =
            new ConcurrentLinkedQueue<>();

    public void recordBefore(String id) { before.add(id); }
    public void recordCommitted(String id) { committed.add(id); }
    public void recordRolledBack(String id) { rolledBack.add(id); }

    public List<String> before() { return List.copyOf(before); }
    public List<String> committed() { return List.copyOf(committed); }
    public List<String> rolledBack() { return List.copyOf(rolledBack); }

    public void clear() {
        before.clear();
        committed.clear();
        rolledBack.clear();
    }
}
~~~

The probe serves tests only, not as a durable audit or production event store. The queues are thread-safe for add/snapshot operations, though `clear()` could race with callbacks if tests ran in parallel; the lab runs sequentially by default, with each test resetting state cleanly.

### 6.12. AuditWriter.java

~~~java
package com.example.aftercommit;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {

    private final AuditEntryRepository repository;

    public AuditWriter(AuditEntryRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(PurchasePlaced event) {
        repository.saveAndFlush(
                new AuditEntry(event.purchaseId(), "AFTER_COMMIT"));
    }
}
~~~

The new transaction takes effect when the callback runs after the purchase commits. Tests will assert that `AuditEntry` exists after the callback rather than merely verifying the method was called.

### 6.13. CommitListener.java

~~~java
package com.example.aftercommit;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommitListener {

    private final LifecycleLog log;
    private final AuditWriter auditWriter;

    public CommitListener(LifecycleLog log, AuditWriter auditWriter) {
        this.log = log;
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(PurchasePlaced event) {
        log.recordBefore(event.purchaseId());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchasePlaced event) {
        auditWriter.record(event);
        log.recordCommitted(event.purchaseId());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(PurchasePlaced event) {
        log.recordRolledBack(event.purchaseId());
    }
}
~~~

Because the listener is not `@Async`, callbacks in the lab run synchronously as the transaction manager processes completion. The order among callback phases matches the description, though never assert strict ordering across multiple independent listeners unless `@Order` is part of the application contract.

### 6.14. RealCommitLifecycleTest.java

`src/test/java/com/example/aftercommit/RealCommitLifecycleTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class RealCommitLifecycleTest {

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;
    @Autowired ApplicationEventPublisher events;

    @BeforeEach
    void prepare() {
        audits.deleteAll();
        purchases.deleteAll();
        log.clear();
    }

    @AfterEach
    void cleanup() {
        audits.deleteAll();
        purchases.deleteAll();
        log.clear();
    }

    @Test
    void afterCommitRunsOnlyAfterSuccessfulTransaction() {
        String id = "REAL-COMMIT-1";

        checkout.place(id);

        assertThat(purchases.findById(id)).isPresent();
        assertThat(audits.findById(id))
                .isPresent()
                .get()
                .extracting(AuditEntry::getAction)
                .isEqualTo("AFTER_COMMIT");

        assertThat(log.before()).containsExactly(id);
        assertThat(log.committed()).containsExactly(id);
        assertThat(log.rolledBack()).isEmpty();
    }

    @Test
    void rollbackNeverTriggersSuccessTask() {
        String id = "REAL-ROLLBACK-1";

        assertThatThrownBy(() -> checkout.placeAndFail(id))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("simulated failure");

        assertThat(purchases.findById(id)).isEmpty();
        assertThat(audits.findById(id)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).containsExactly(id);
    }

    @Test
    void publishingOutsideTransactionIsIgnoredByDefault() {
        events.publishEvent(new PurchasePlaced("NO-TX-1"));

        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).isEmpty();
        assertThat(audits.findById("NO-TX-1")).isEmpty();
    }
}
~~~

This class **has no test-level `@Transactional`**, so the service executes its own transaction and commits before returning (synchronous listener). `@BeforeEach`/`@AfterEach` actually clean up via repository transactions. The rollback test proves the purchase did not commit and the success callback was never invoked. The no-transaction test protects default `fallbackExecution=false`.

### 6.15. DefaultRollbackSliceTest.java

`src/test/java/com/example/aftercommit/DefaultRollbackSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class DefaultRollbackSliceTest {

    private static final String ID = "SLICE-ROLLBACK-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    void defaultRollbackSkipsAfterCommit() {
        assertThat(TestTransaction.isActive()).isTrue();

        checkout.place(ID);

        assertThat(purchases.findById(ID)).isPresent();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).isEmpty();
    }

    @AfterTransaction
    void after() {
        assertThat(purchases.findById(ID)).isEmpty();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).containsExactly(ID);
        log.clear();
    }
}
~~~

`@Import` adds only the beans not scanned by `@DataJpaTest`. `@AfterTransaction` runs after the outer rollback and sees that `AFTER_ROLLBACK` was handled. The test seeing `PurchaseRecord` **inside T1** does not prove commit.

### 6.16. ExplicitCommitSliceTest.java

`src/test/java/com/example/aftercommit/ExplicitCommitSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class ExplicitCommitSliceTest {

    private static final String ID = "SLICE-COMMIT-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    @Commit
    void writesButHasNotCommittedInsideMethod() {
        checkout.place(ID);

        assertThat(purchases.findById(ID)).isPresent();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
    }

    @AfterTransaction
    void afterCommitAndCleanup() {
        try {
            assertThat(purchases.findById(ID)).isPresent();
            assertThat(audits.findById(ID))
                    .isPresent()
                    .get()
                    .extracting(AuditEntry::getAction)
                    .isEqualTo("AFTER_COMMIT");
            assertThat(log.before()).containsExactly(ID);
            assertThat(log.committed()).containsExactly(ID);
            assertThat(log.rolledBack()).isEmpty();
        }
        finally {
            audits.deleteById(ID);
            purchases.deleteById(ID);
            log.clear();
        }
    }
}
~~~

Important: `@Commit` tells TestContext to commit **after the method ends**, not immediately when `checkout.place` returns inside outer T1. Asserting inside `@AfterTransaction` verifies the `AFTER_COMMIT` callback. Committed data must be cleaned up outside T1.

### 6.17. ManualCommitSliceTest.java

`src/test/java/com/example/aftercommit/ManualCommitSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class ManualCommitSliceTest {

    private static final String ID = "MANUAL-COMMIT-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    void commitsAtChosenPoint() {
        assertThat(TestTransaction.isActive()).isTrue();

        try {
            checkout.place(ID);
            assertThat(log.committed()).isEmpty();

            TestTransaction.flagForCommit();
            TestTransaction.end();

            assertThat(TestTransaction.isActive()).isFalse();
            assertThat(purchases.findById(ID)).isPresent();
            assertThat(audits.findById(ID)).isPresent();
            assertThat(log.committed()).containsExactly(ID);
        }
        finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            audits.findById(ID).ifPresent(audits::delete);
            purchases.findById(ID).ifPresent(purchases::delete);
            log.clear();
        }
    }
}
~~~

`TestTransaction.end()` ends the active test-managed transaction per the commit flag. In `finally`, if an error occurred before `end()`, the test rolls back T1 before cleaning fixtures; if already committed, cleanup runs via separate repository transactions. `@Commit` is not needed when committing manually.

### 6.18. Running the Test Classes

Inside `after-commit-event-lab`:

~~~bash
mvn -q clean test

mvn -q -Dtest=RealCommitLifecycleTest test
mvn -q -Dtest=DefaultRollbackSliceTest test
mvn -q -Dtest=ExplicitCommitSliceTest test
mvn -q -Dtest=ManualCommitSliceTest test
~~~

Requires JDK 17+, Maven, and reachable dependency repositories. Reports are under `target/surefire-reports`. These test classes are designed to PASS with the code/schema above; **do not claim Maven was executed while writing this article**. On failure, read the root cause/stack trace and check the Spring context, transaction boundary, and actual rows before altering expectations.

## 7. Expected Results Table

| Test class | Transaction boundary | `AFTER_COMMIT` check | Post-test data |
| --- | --- | --- | --- |
| `RealCommitLifecycleTest` | Service commits/rolls back on its own | Runs after commit, does not run after rollback | Cleaned in `@AfterEach` |
| `DefaultRollbackSliceTest` | Test T1 rolls back by default | Does not run; `AFTER_ROLLBACK` runs | T1 rolls back |
| `ExplicitCommitSliceTest` | T1 commits after method due to `@Commit` | Runs before `@AfterTransaction` | Cleaned in `@AfterTransaction` |
| `ManualCommitSliceTest` | Commits right at `TestTransaction.end()` | Checked after `end` | Cleaned in `finally` |

Anti-false-positive point: each positive test checks both **rows in the database** and **post-commit logs**; the rollback test verifies **no row** and **no audit**. Distinguish `BEFORE_COMMIT` and `AFTER_COMMIT` at the right phases. Never depend on JUnit method ordering.

## 8. Synchronous Listeners, @Async, and Awaiting Results

### 8.1. Synchronous in the Demo

`@TransactionalEventListener` in the lab has no `@Async`, so callbacks execute during the service's transaction completion. Right after `checkout.place(id)` returns in the full-context test without outer T1, you can assert `LifecycleLog` and the audit row.

Still, a synchronous callback does not guarantee an email, SMS, or broker message was received by an external system if the callback only enqueues/schedules a job.

### 8.2. If Adding @Async

~~~java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void send(PurchasePlaced event) {
    emailGateway.send(event.purchaseId());
}
~~~

This is a snippet requiring `@EnableAsync`, an executor, and a suitable fake/email gateway. Once the transaction commits, the callback may **be scheduled**, which does not mean the async task finished by the time the service returns.

Tests like the following are easily flaky:

~~~java
checkout.place("P-ASYNC");
assertThat(fakeMail.sent()).isTrue();
~~~

If `fakeMail` is updated from a worker thread, the assertion can run first. Use `CountDownLatch`/`CompletableFuture` or a bounded await.

### 8.3. CountDownLatch for a Fake Outbound Adapter

~~~java
CountDownLatch delivered = new CountDownLatch(1);
AtomicReference<String> sent = new AtomicReference<>();

// Inside the fake gateway called by the async listener:
// sent.set(event.purchaseId());
// delivered.countDown();

// After the original transaction committed:
assertThat(delivered.await(3, TimeUnit.SECONDS)).isTrue();
assertThat(sent.get()).isEqualTo("P-ASYNC");
~~~

This snippet needs imports and fake gateway/fixture classes. Never use `Thread.sleep(500)` to guess the worker ran. When a test must prove rollback does not dispatch a task, verify task scheduling/fake gateway along the rollback path with a reasonable bounded interval rather than blindly asserting "not seen yet right away."

### 8.4. "Enqueued" Differs from "Executed"

An `AFTER_COMMIT` listener calling `taskExecutor.execute(job)`: an assertion verifying the executor received the job only proves **enqueueing/scheduling**. A separate test must verify the job handler executes and check its outcome. If a task runs after a 30-second delay, use a fake clock/scheduler in unit tests instead of waiting a real 30 seconds.

## 9. Transactional Outbox and Reliability

### 9.1. The Gap Between Commit and Publish

~~~text
Database transaction COMMIT SUCCESS
        |
        |  <-- JVM crash here:
        |      event never sent to broker
        v
AFTER_COMMIT listener publishes
        |
        v
Broker receives message
~~~

`@TransactionalEventListener(AFTER_COMMIT)` prevents sending **before** commit, yet gives no guarantee **against event loss if the process crashes**. Even when the callback runs, broker retries/failed ACKs can cause duplicate sends.

### 9.2. Transactional Outbox

Instead of publishing only an in-memory event:
1. Inside **the same transaction T1**, write the business row and an outbox row `PENDING`.
2. Commit T1; both rows become visible.
3. The `AFTER_COMMIT` callback can wake the relay immediately.
4. A periodic relay also scans `PENDING` rows after restarts.
5. The relay sends messages and updates status or retries with backoff.
6. Consumers deduplicate by `eventId`/idempotency key.

~~~text
T1:
  INSERT purchase
  INSERT outbox(event_id, payload, status=PENDING)
  COMMIT
      |
      +-- wake relay (AFTER_COMMIT, optimizes latency)
      |
      +-- relay can poll committed rows even if callback was lost
          |
          +-- publish
          +-- mark delivered/retry
~~~

When the business **cannot afford to lose notifications**, an outbox is a far stronger architecture than keeping events only in RAM.

### 9.3. Service Pseudocode with Outbox

~~~java
@Transactional
public void place(String id) {
    purchases.save(new PurchaseRecord(id, "PLACED"));
    outbox.save(new OutboxEvent(
            UUID.randomUUID().toString(),
            "PURCHASE_PLACED",
            id,
            "PENDING"));
    events.publishEvent(new OutboxReady(id));
}
~~~

This is an architectural snippet **not in the runnable lab** because `OutboxEvent`, `OutboxReady`, and the repository are not defined. The key feature is **both INSERTs inside T1**, rather than writing to the outbox inside an `AFTER_COMMIT` listener.

### 9.4. Testing Outbox Across Layers

- Rollback of T1: no business row, no outbox row.
- Commit of T1: both rows exist, `eventId`/payload match.
- Relay in a fresh transaction reads the committed row.
- Broker temporarily down: row stays pending, retry policy applies.
- Crash after publish before status update: may resend; consumer is idempotent.
- Process restart: relay picks up pending rows.
- Duplicate event/request: unique constraints/idempotency keys enforce safety.

Never claim "exactly once" solely because `@TransactionalEventListener` or `REQUIRES_NEW` is present.

## 10. Post-Commit Exceptions and Failure Boundaries

### 10.1. When the Listener Fails, the Original Transaction Is Already Finished

Suppose:

~~~text
T1: save purchase -> COMMIT succeeds
AFTER_COMMIT: emailGateway.send -> network error
~~~

The purchase row **already committed**. A listener exception cannot roll back the original transaction after commit. Whether the exception propagates back to the caller or is merely logged depends on the synchronization/event/executor type; do not write tests assuming all post-commit exceptions are thrown out of the service method.

### 10.2. AuditWriter Can Fail Independently

`AuditWriter.record` uses `REQUIRES_NEW`. If it fails to commit (unique constraint, database down, timeout), the original purchase remains committed. When the audit is mandatory and must be atomic with the purchase, write the audit record or outbox row **inside T1** rather than only in a post-commit callback.

### 10.3. Retries and Idempotency

When sending external notifications:
- Use a stable `eventId`/`operationId`.
- Cap max attempts and use backoff.
- Distinguish retryable transport errors from permanent validation errors.
- Persist delivery state if tasks cannot be lost.
- Never retry indefinitely inside a transaction-completion callback, blocking threads and inflating latency.
- If the provider lacks idempotency support, consumers/business logic need a deduplication strategy.

### 10.4. Recording Metrics Accurately

Do not count "transaction success" merely because `publishEvent` succeeded. Record commit success at the corresponding phase, and delivery success separately when the external adapter confirms. Commit can succeed while delivery fails; dashboards should never conflate the two.

## 11. ThreadLocal and AOP Traps

### 11.1. Self-Invocation Neutralizes @Transactional

~~~java
public void place() {
    this.saveWithTransaction();
}

@Transactional
public void saveWithTransaction() {
    // ...
}
~~~

In Spring proxy-based AOP, calling a method via `this.` can **bypass the proxy**, failing to open a transaction. Publishing an event outside a transaction causes default `AFTER_COMMIT` listeners not to run. Invoke through a Spring-proxied bean or use `TransactionTemplate` when explicit transactions are needed.

### 11.2. REQUIRES_NEW Must Go Through a Proxy

Similarly, `@Transactional(propagation = REQUIRES_NEW)` on a method inside the same listener called via `this.write(...)` does not create a new transaction. The demo extracts `AuditWriter` into its own bean.

### 11.3. @Async / New Threads

Imperative Spring transactions typically use `ThreadLocal`. Work executing on `@Async`, `CompletableFuture`, or executor threads does not automatically inherit the JUnit thread's test-managed transaction. Events published inside a worker bind to that worker's transaction (or none); test that exact boundary.

### 11.4. assertTimeoutPreemptively

Spring TestContext documentation warns that JUnit `assertTimeoutPreemptively(...)` can execute the callback on another thread, outside the `ThreadLocal`-bound test transaction. Database writes inside the callback can commit beyond outer rollback.

~~~java
// Pattern requiring caution, not part of the runnable project.
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    checkout.place("P-TIMEOUT");
});
~~~

Avoid preemptive timeouts in transactional tests when relying on rollback for cleanup. Use non-preemptive `assertTimeout`, test-level database isolation, and bounded operation timeouts instead.

### 11.5. @SpringBootTest(RANDOM_PORT)

A real HTTP request:
- The JUnit test thread may hold a test-managed transaction.
- The HTTP server handles requests on a separate worker thread.
- The server-side service opens/commits its own transaction.
- Rolling back the test thread **does not undo** server-side database writes.

By contrast, `MockMvc` normally handles requests on the test thread, so `REQUIRED` services can join the outer test transaction. Do not assume identical behavior across both setups. With `RANDOM_PORT`, clean up rows explicitly via repository/service after requests.

### 11.6. Multiple Transaction Managers

When two datasources exist, `@Transactional(transactionManager="orderTx")` does not automatically manage resources belonging to `auditTx`. A `@Commit` on one manager does not guarantee all external/broker resources commit too. Integration tests must specify the chosen transaction manager and datasource.

## 12. Cases Requiring Separate Testing in Production-Like Environments

### 12.1. Commit-Time Constraints

PostgreSQL supports `DEFERRABLE` constraints; errors may only surface at commit. `saveAndFlush` in a rolling-back H2 test does not prove commit-time correctness. Use PostgreSQL/Testcontainers and assert exceptions at `TestTransaction.end()` or the service transaction boundary.

### 12.2. Transaction Isolation, Read Replicas, and Index Lag

Immediately after primary DB commit, a read replica or search index may lag behind. When testing listeners reading from replicas, results can be eventually consistent. Never use H2 unit tests to assert real replica latency. Use bounded polling, test containers/clusters, and clear SLAs.

### 12.3. External Brokers/Email

Mocks/fakes verify `after-commit` scheduling, yet cannot verify TLS/auth/SDK behavior. Use authorized sandboxes/integration tests for brokers, SMTP, or HTTP providers, and never send real payment or transactional emails from test suites.

### 12.4. Listener Performing DB Writes and Deadlocking

If a callback opens a new transaction while the old transaction still holds connections/resources, multi-threaded tests can expose connection pool exhaustion or lock contention. Ensure pool sizing, timeouts, and avoid nested independent transactions when writing an outbox row inside T1 works instead.

### 12.5. Listener Receiving a Stale Entity

If an event carries a JPA entity with lazy fields and the callback runs after commit, accessing those fields can trigger lazy-loading/transaction errors. Send IDs/immutable snapshots and re-query inside `REQUIRES_NEW(readOnly=true)` if needed.

## 13. Common Issues and Diagnostics

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Listener does not run in `@DataJpaTest` | Test rolls back by default | `@Commit`/`TestTransaction`, assert after commit |
| `@Commit` yet listener is empty in test body | Commit occurs only after method ends | `@AfterTransaction` or `TestTransaction.end()` |
| Listener does not run in full context | Event published outside tx, proxy bypassed, bean not scanned | Check active tx, `@Transactional`, event type, imports |
| Listener runs on rollback | `@EventListener` used or gateway called directly before commit | Switch to right phase, add rollback test |
| Post-commit audit DB write missing | Reused old transaction resources without new commit | Separate `REQUIRES_NEW` bean called through proxy |
| Data saved in test T1 unseen by next test | Rollback/visibility | Verify post-commit in a new transaction |
| Next test fails on duplicate key | `@Commit` left row behind | Clean up outside T1 / isolated DB |
| Async test is flaky | Asserted before worker finished | Bounded latch/future/await |
| Service succeeds yet email fails | External post-commit error | Retry/outbox, check delivery outcome separately |
| Callback throws yet purchase persists | Original commit already succeeded | Do not expect rollback after commit |
| Event ignored outside transaction | `fallbackExecution=false` | Add real transaction or intentional fallback |
| Event processed twice | Retry/duplicate publish | Idempotency keys, unique constraints, consumer dedupe |
| `@AfterTransaction` does not run | Test has no test-managed transaction | Use test `@Transactional` or `@DataJpaTest` properly |
| `assertTimeoutPreemptively` leaks rows | Different thread does not inherit T1 | Change timeout strategy/test cleanup |
| `RANDOM_PORT` test leaves DB row | Server transaction runs on different thread | Explicit cleanup/isolated DB |
| H2 passes, PostgreSQL commit fails | Different engine/deferred constraints | Testcontainers with production DB |

When debugging, record the event type, transaction manager, whether a transaction is active at publish time, the phase annotation, whether the listener bean is present in context, the test rollback/commit strategy, and actual database rows. **Never** change expected to match a broken actual when business requirements demand post-commit execution.

## 14. Practice Exercises

1. Write `@TransactionalEventListener(AFTER_COMMIT)` and a fake notification gateway. Test both happy path and rollback.
2. Run `@DataJpaTest` with default rollback and explain why the `AFTER_COMMIT` callback never runs.
3. Add `@Commit`, move assertions from `@Test` to `@AfterTransaction`, and add cleanup.
4. Replace `@Commit` with `@Rollback(false)` and compare semantics.
5. Use `TestTransaction.flagForCommit()` and `end()` to commit mid-test, then query fresh state.
6. Add `BEFORE_COMMIT` and `AFTER_ROLLBACK` listeners and verify which callbacks execute on each path.
7. Publish an event outside a transaction. Try `fallbackExecution=true` and distinguish fallback from a successful commit.
8. Write a `REQUIRES_NEW` audit writer bean and verify the audit row persists after a real commit.
9. Call the writer via self-invocation and explain why the AOP proxy does not apply.
10. Convert the listener to `@Async` and replace `Thread.sleep` with `CountDownLatch`.
11. Simulate a gateway failure after commit. Verify the business row remains and delivery failure is recorded.
12. Create an outbox row in the same transaction as the purchase and test that rollback leaves no outbox row.
13. Simulate a crash after commit and before publish; explain how a relay retries pending outbox rows.
14. Try `@SpringBootTest(RANDOM_PORT)` and evaluate why test-level rollback does not cover HTTP server threads.
15. If the database has a `DEFERRABLE` constraint, plan a commit-time failure test using PostgreSQL/Testcontainers.
16. Write a duplicate-event test with an idempotency key and confirm no duplicate notification fires.
17. Draft a callback ordering and cleanup checklist for tests running in parallel across multiple transactions.

## 15. Pre-Merge Checklist

- [ ] Is the event published inside an active transaction or outside a transaction?
- [ ] Does `@TransactionalEventListener` specify the right phase?
- [ ] Is `fallbackExecution` understood and tested when needed?
- [ ] Are service methods invoked through Spring proxies?
- [ ] Are `saveAndFlush` and `commit` not conflated?
- [ ] In `@DataJpaTest`, is default rollback accounted for?
- [ ] Do commit tests use `@Commit`/`@Rollback(false)` or `TestTransaction`?
- [ ] Are post-commit assertions placed in `@AfterTransaction` or after `end()`?
- [ ] Are both positive commit and negative rollback cases tested?
- [ ] Are both committed DB state and post-commit outcomes asserted?
- [ ] Do post-commit DB writers go through a `REQUIRES_NEW` bean?
- [ ] Are external side effects avoided before commit?
- [ ] For async listeners, do tests await completion with a bounded timeout?
- [ ] Is task enqueued distinguished from task completed?
- [ ] Is committed data cleaned up in a separate transaction?
- [ ] Is `@DirtiesContext` avoided as a DB cleanup substitute?
- [ ] Are idempotency/retries/durable outbox in place if events cannot be lost?
- [ ] Are commit success and email/broker delivery success tracked separately?
- [ ] With real HTTP, is server-write cleanup not entrusted to test rollback?
- [ ] Are preemptive timeouts avoided when tests rely on `ThreadLocal` transactions?
- [ ] Are production DB semantics tested on an appropriate engine when needed?
- [ ] Did Maven/JUnit run in CI with Surefire reports inspected?

**Conclusion:** `@TransactionalEventListener(AFTER_COMMIT)` ensures a listener fires only after a transaction commits successfully, yet `@DataJpaTest`'s default rollback can prevent tests from ever exercising that path. Use `@Commit`/`@AfterTransaction` or `TestTransaction.end()` to create a real commit boundary. When a post-commit task writes to the database, handle old transaction resources carefully and typically extract the writer into `REQUIRES_NEW`. If post-commit side effects must never be lost, add a transactional outbox, retries, and idempotency rather than treating an in-memory listener as a delivery guarantee.

## 16. Official References

- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2 — `TransactionSynchronization` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework 6.2 — `TestTransaction` API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 — `@AfterTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-aftertransaction.html
- Spring Framework 6.2 — `@Commit` and `@Rollback`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-commit.html
- Spring Boot 3.5 — `@DataJpaTest`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
