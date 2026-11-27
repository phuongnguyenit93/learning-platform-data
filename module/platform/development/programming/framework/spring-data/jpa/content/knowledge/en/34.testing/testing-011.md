# Testing Auditing, Callbacks, and After-Commit Events in Spring Data JPA

A Spring Data JPA application often needs to verify three related but distinct behaviors:

- **Auditing** automatically records who created or modified an entity and when.
- **JPA lifecycle callbacks** run around individual entity persist, update, and remove operations.
- **After-commit events** run once a transaction has committed successfully, suitable for triggering follow-up work like sending notifications or scheduling downstream processing.

These mechanisms have different execution timing and purposes. A proper test must prove audit fields are populated, callbacks fire when entities flush, and `AFTER_COMMIT` listeners execute only after a transaction genuinely commits. Examples in this article use Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ, and H2.

## 1. Distinguishing Auditing, Callbacks, and Transaction Events

| Mechanism | Timing | Purpose |
|---|---|---|
| Spring Data Auditing | When an entity is created or updated via JPA lifecycle | Record created/modified dates and auditor |
| JPA callbacks such as `@PrePersist`, `@PostUpdate` | Around an entity's persist/update/remove operations | Normalize or validate entity state |
| `@TransactionalEventListener(AFTER_COMMIT)` | After the transaction commits successfully | Trigger work dependent on committed data |

Do not treat `@PostPersist` as a post-commit event. That callback runs after the `INSERT` statement executes, yet the transaction can still roll back afterward. When reacting strictly to committed transactions, use a transaction-bound event.

Spring Data Auditing also relies on a JPA entity listener. It handles common metadata fields, whereas custom callbacks hold entity-lifecycle logic. Transaction events operate at the transaction boundary rather than the individual entity boundary.

## 2. Configuring Spring Data Auditing

Spring Data JPA provides these annotations:

- `@CreatedDate`: entity creation timestamp.
- `@LastModifiedDate`: most recent modification timestamp.
- `@CreatedBy`: user who created the entity.
- `@LastModifiedBy`: user who last modified the entity.

These annotations live in `org.springframework.data.annotation`. To process them in JPA, attach `AuditingEntityListener` and enable `@EnableJpaAuditing`.

Create a shared superclass:

**AuditableEntity.java**

```java
package com.example.audit;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    @Column(updatable = false, nullable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

Entity extending the superclass:

**AuditNote.java**

```java
package com.example.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_notes")
public class AuditNote extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String content;

    protected AuditNote() {
    }

    public AuditNote(String content) {
        this.content = content;
    }

    public Long getId() {
        return id;
    }

    public String getContent() {
        return content;
    }

    public void changeContent(String content) {
        this.content = content;
    }
}
```

Enable auditing in application configuration:

**JpaAuditConfig.java**

```java
package com.example.audit;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration(proxyBeanMethods = false)
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditConfig {
}
```

Declare `AuditorAware` so Spring Data knows who is performing operations:

**AuditorConfig.java**

```java
package com.example.audit;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration(proxyBeanMethods = false)
public class AuditorConfig {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system-user");
    }
}
```

In production, the auditor value is typically read from the authenticated user in `SecurityContext`, or from a background job's context. Do not hard-code `system-user` if real user attribution is needed. When no user is present, return `Optional.empty()` or a system actor according to application conventions.

`@EnableJpaAuditing` and the `AuditorAware` bean can reside in the same configuration class. Splitting them in the example makes substituting the auditor in tests easier. If the application already enables auditing in production configuration, avoid enabling a duplicate configuration in tests.

## 3. Testing Auditing With @DataJpaTest

`@DataJpaTest` builds a JPA-focused Spring context configuring repositories/entities and usually using an embedded database when available. Because the test slice has a narrow scope, auditing configuration may need to be imported explicitly.

Fixed auditor configuration for tests:

**AuditingTestConfig.java**

```java
package com.example.audit;

import java.util.Optional;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@TestConfiguration(proxyBeanMethods = false)
@EnableJpaAuditing(auditorAwareRef = "testAuditorAware")
public class AuditingTestConfig {

    @Bean
    AuditorAware<String> testAuditorAware() {
        return () -> Optional.of("integration-test");
    }
}
```

Test class:

**AuditNoteTest.java**

```java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(AuditingTestConfig.class)
class AuditNoteTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void fillsCreatedAndModifiedAuditFields() {
        AuditNote note = new AuditNote("first version");

        entityManager.persistAndFlush(note);

        assertThat(note.getCreatedBy()).isEqualTo("integration-test");
        assertThat(note.getLastModifiedBy()).isEqualTo("integration-test");
        assertThat(note.getCreatedAt()).isNotNull();
        assertThat(note.getLastModifiedAt()).isNotNull();

        Instant createdAt = note.getCreatedAt();

        note.changeContent("second version");
        entityManager.flush();

        assertThat(note.getCreatedBy()).isEqualTo("integration-test");
        assertThat(note.getLastModifiedBy()).isEqualTo("integration-test");
        assertThat(note.getCreatedAt()).isEqualTo(createdAt);
        assertThat(note.getLastModifiedAt()).isAfterOrEqualTo(createdAt);
    }
}
```

The assertions verify:

1. Upon persisting and flushing, created date/by and modified date/by are populated.
2. Upon modifying a property and flushing, last modified is updated.
3. Created date/by remain unchanged after the update.

Call `flush()` to force JPA to synchronize changes to the database and trigger lifecycle listeners immediately during the test. Calling only `persist()` or `save()` may not execute SQL immediately because JPA can defer until flush or commit.

Slice tests run by default inside transactions that roll back after each test. That does not hinder testing auditing and callbacks, since they execute during persist/update and flush prior to rollback.

## 4. Testing JPA Lifecycle Callbacks

JPA callbacks fit small, synchronous logic tightly bound to an individual entity. For example: normalizing a string before insert or recording when an entity was updated.

**CallbackArticle.java**

```java
package com.example.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Locale;

@Entity
@Table(name = "callback_articles")
public class CallbackArticle {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    private String normalizedTitle;

    private Instant updatedAt;

    protected CallbackArticle() {
    }

    public CallbackArticle(String title) {
        this.title = title;
    }

    public String getNormalizedTitle() {
        return normalizedTitle;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void rename(String title) {
        this.title = title;
    }

    @PrePersist
    void beforeInsert() {
        normalizedTitle = title == null
            ? null
            : title.trim().toLowerCase(Locale.ROOT);
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Callback test:

**CallbackArticleTest.java**

```java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CallbackArticleTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void invokesPrePersistAndPreUpdate() {
        CallbackArticle article =
            new CallbackArticle("  Spring Data JPA  ");

        entityManager.persistAndFlush(article);

        assertThat(article.getNormalizedTitle())
            .isEqualTo("spring data jpa");

        article.rename("JPA callbacks");
        entityManager.flush();

        assertThat(article.getUpdatedAt()).isNotNull();
    }
}
```

`@PrePersist` runs before `INSERT`; `@PreUpdate` runs before `UPDATE`. Other callbacks include `@PostPersist`, `@PostUpdate`, `@PreRemove`, and `@PostRemove`. Callbacks can live directly inside the entity or in a separate class registered via `@EntityListeners`.

Keep callbacks short and modify only appropriate state on the entity itself. Avoid calling repositories, querying `EntityManager`, sending HTTP/emails, or performing external work inside callbacks. Those actions make the persistence lifecycle unpredictable and offer no guarantee the transaction will ultimately commit. If a callback throws a runtime exception inside a transaction, the persistence operation can fail and roll back the transaction.

## 5. Publishing Events in a Transaction and Handling AFTER_COMMIT

Suppose an application wants to send a notification when creating an invoice. Sending an email straight inside the service method could fire a notification even if the transaction saving the invoice later rolls back.

Instead, the service publishes an application event inside the transaction. A listener annotated with `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` processes it only if the transaction commits successfully.

Event:

**InvoiceCreatedEvent.java**

```java
package com.example.invoice;

public record InvoiceCreatedEvent(Long invoiceId) {
}
```

Entity and repository:

**Invoice.java**

```java
package com.example.invoice;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }

    public Long getId() {
        return id;
    }
}
```

**InvoiceRepository.java**

```java
package com.example.invoice;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository
        extends JpaRepository<Invoice, Long> {
}
```

Service persisting the entity and publishing the event:

**InvoiceService.java**

```java
package com.example.invoice;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public InvoiceService(
            InvoiceRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long create(String invoiceNumber) {
        Invoice invoice =
            repository.saveAndFlush(new Invoice(invoiceNumber));

        eventPublisher.publishEvent(
            new InvoiceCreatedEvent(invoice.getId())
        );

        return invoice.getId();
    }
}
```

Listener:

**InvoiceCreatedListener.java**

```java
package com.example.invoice;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class InvoiceCreatedListener {

    private final List<Long> handledInvoiceIds =
        new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onInvoiceCreated(InvoiceCreatedEvent event) {
        handledInvoiceIds.add(event.invoiceId());
    }

    public List<Long> handledInvoiceIds() {
        return List.copyOf(handledInvoiceIds);
    }
}
```

The event is published before the transaction ends, while the listener is invoked after commit. If the transaction rolls back, the `AFTER_COMMIT` listener is not called. If an event is published outside a transaction, transaction-bound listeners do not run by default; setting `fallbackExecution = true` alters that behavior, though enable it only when business logic genuinely wants handling even without a transaction.

Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Choose the phase matching business timing. Standard `@EventListener` handles events immediately upon publication without waiting for commit.

## 6. Testing After-Commit Events and Rollback

A common pitfall: `@DataJpaTest` runs each test inside a Spring Test-managed transaction by default and rolls back when finished. Because the transaction never commits, `AFTER_COMMIT` listeners will not fire within the test body.

To test a real commit, disable the test-managed transaction for the test method. Then calling the service opens its own transaction via proxy; the service commits before returning, and synchronous listeners run before the test continues.

**InvoiceAfterCommitTest.java**

```java
package com.example.invoice;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
@Import({InvoiceService.class, InvoiceCreatedListener.class})
class InvoiceAfterCommitTest {

    @Autowired
    private InvoiceService invoiceService;

    @Autowired
    private InvoiceCreatedListener listener;

    @Autowired
    private InvoiceRepository repository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private ApplicationEventPublisher eventPublisher;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void handlesEventAfterServiceTransactionCommits() {
        Long id = invoiceService.create("INV-2026-001");

        assertThat(repository.findById(id)).isPresent();
        assertThat(listener.handledInvoiceIds()).containsExactly(id);
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void doesNotHandleEventWhenTransactionRollsBack() {
        TransactionTemplate transaction =
            new TransactionTemplate(transactionManager);

        transaction.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );

        transaction.executeWithoutResult(status -> {
            eventPublisher.publishEvent(
                new InvoiceCreatedEvent(-1L)
            );
            status.setRollbackOnly();
        });

        assertThat(listener.handledInvoiceIds()).doesNotContain(-1L);
    }
}
```

In the commit test, the service is called through its proxied Spring bean, so `@Transactional` opens and commits the transaction. Because listeners run synchronously by default, once `create()` returns, the list already contains the invoice ID.

In the rollback test, the event is published inside an active transaction, yet the transaction is marked rollback-only. The `AFTER_COMMIT` listener does not run, so test ID `-1L` never appears in the list.

If keeping the default test transaction, the test does not commit at the end of the method body, so assertions inside the test will observe the listener has not run yet. You can use `@Commit` or `TestTransaction.flagForCommit()` and `TestTransaction.end()`, though when verifying immediately after service commit, disabling the test transaction makes boundaries clearer.

If a listener is annotated with `@Async`, processing runs on another executor and may complete after the service returns. In that case, tests must wait conditionally via proper synchronization; avoid fixed sleeps that cause flaky tests.

## 7. Writing New Data Inside an After-Commit Listener

Once `AFTER_COMMIT` executes, the original transaction has already completed. Persistence resources may remain bound to the thread during callback completion, yet database changes made at this point will not be committed as part of the completed transaction.

If the listener needs to persist additional data, call a separate service that opens a new transaction:

```java
@Service
public class NotificationLogService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordSent(Long invoiceId) {
        // Persist notification log in a new transaction.
    }
}
```

The listener injects `NotificationLogService` and calls this method. Use a separate Spring bean so the invocation passes through the transaction proxy; calling another `REQUIRES_NEW` method on the same object via self-invocation will not activate the proxy as intended.

You can combine `@Async` when separating notification delivery from the commit thread:

```java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendInvoiceNotice(InvoiceCreatedEvent event) {
    // Delegate to a notification service.
}
```

Enable `@EnableAsync` and configure an appropriate executor. Errors inside async tasks are not propagated back to the committed request; implement dedicated logging, retries, and monitoring.

## 8. AFTER_COMMIT Does Not Replace a Durable Queue

Transaction-bound events guarantee listeners fire only after commit within the current process. They are not a message broker and do not persist events durably. If the application crashes after committing but before the listener finishes, follow-up work can be lost.

For critical emails, webhooks, or messages requiring delivery guarantees, consider a transactional outbox:

1. Within the same business transaction, save the invoice and an outbox record describing the event.
2. Commit both together.
3. A worker reads unprocessed outbox records and dispatches messages.
4. Mark records processed upon successful delivery; support retries and idempotency to avoid duplicate processing.

An `AFTER_COMMIT` event can wake the worker as an optimization, while the outbox record remains the durable source of truth for recovery on restart.

## 9. Common Issues and How to Check

| Symptom | Common Cause | Resolution |
|---|---|---|
| Created/modified fields are always null | Auditing not enabled, missing `AuditingEntityListener`, or missing `AuditorAware` | Check `@EnableJpaAuditing`, listener, and auditor bean |
| `CreatedBy` populated but `LastModifiedBy` blank | `AuditorAware` returns empty or user context is absent at flush | Check actor source and execution timing |
| Callback does not fire in tests | Not flushed or entity did not produce an actual UPDATE | Use `persistAndFlush`, change a property, then flush |
| `AFTER_COMMIT` listener does not run in `@DataJpaTest` | Test-managed transaction rolled back instead of committing | Disable test transaction or explicitly end test transaction with commit |
| Listener runs despite business failure | Used immediate `@EventListener` instead of transaction-bound listener | Use `@TransactionalEventListener` with the appropriate phase |
| DB writes inside listener do not appear | Executing inside an already-committed transaction | Call a separate service with `REQUIRES_NEW` |
| Async events fail intermittently in tests | Test asserts before executor completes | Use a latch, future, or bounded wait condition |
| Notifications lost on process crash | In-process events lack durable storage | Use a transactional outbox and retry mechanism |

## 10. Checklist for the Test Suite

- **Auditing:** test both persist and update; confirm created fields remain unchanged and modified fields update.
- **Auditor:** use a deterministic actor in tests for repeatability; test the missing-actor case.
- **Lifecycle callbacks:** flush after persist/update; assert callback-produced changes; do not rely on callbacks to prove commit.
- **Transaction events:** test `AFTER_COMMIT` listeners with a genuinely committed transaction; verify rollback does not trigger the listener.
- **Test slice:** remember `@DataJpaTest` rolls back by default; configure explicitly when tests need commit.
- **Async:** synchronize tests with latches/futures instead of sleep; test executor errors.
- **Durability:** if follow-up work cannot be lost, test the outbox, retries, and idempotency.

Auditing answers who created/modified an entity and when; callbacks handle entity-level lifecycle hooks; transaction events coordinate follow-up work based on commit outcomes. Properly separating these three responsibilities keeps tests accurately aligned with Spring Data JPA behavior and avoids dispatching notifications or writing side data from failed transactions.