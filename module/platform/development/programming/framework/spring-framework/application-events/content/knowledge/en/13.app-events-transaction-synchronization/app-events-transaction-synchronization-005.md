# Persistence Context After Commit in Spring Framework Application Events

## 1. The question: after commit, is EntityManager still usable?

When a `@Transactional` method saves data using JPA and publishes a Spring event, the application often wants to handle the event **only after the transaction commits successfully**. A common approach is registering a listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // Handle after the publishing transaction commits successfully.
}
~~~

*This is an illustrative snippet inside a Spring bean; `OrderCreated` is an application-defined event type.*

A common point of confusion: **"the transaction has committed" does not mean "all JPA resources were immediately closed and unbound from the thread"**. In Spring, at the time of a post-commit callback, transaction resources such as `EntityManager`, `Session`, or the JDBC connection **may still be bound to the thread and accessible** before Spring finishes cleanup. According to the `@TransactionalEventListener` Javadoc, data access at this point may still "participate" in the old transaction context, **but new changes will not be committed to that resource**.

Therefore, the following two statements are **different**:

- **The persistence context is accessible:** for instance, retrieving a managed entity, reading its properties, or seeing the object in the first-level cache.
- **There is a transaction still capable of committing new changes:** after the main commit finishes, there is no subsequent commit pass for modifications just made in that callback.

Practical rule: use `AFTER_COMMIT` to observe committed results or trigger post-commit actions; if you need to **write additional data to the database**, open **a new transaction** explicitly, typically using `@Transactional(propagation = Propagation.REQUIRES_NEW)` on a separate bean.

## 2. Persistence context and transaction are two related but non-identical lifecycles

A **persistence context** is the set of entities managed by an `EntityManager`, along with entity identity management, the first-level cache, and change tracking (dirty checking). A **transaction** is the boundary deciding whether data changes are committed or rolled back.

| Concept | Meaning |
| --- | --- |
| `EntityManager` | JPA API to find, persist, merge, remove, and query entities. |
| Persistence context | State of entities managed in an `EntityManager`, including the first-level cache and pending changes awaiting synchronization. |
| Managed entity | An entity still attached to a persistence context; `EntityManager.contains(entity)` may return `true`. |
| Dirty checking | Mechanism by which a JPA provider, such as Hibernate, detects changes to managed entities upon flush. |
| `flush()` | Synchronizes pending operations to SQL according to provider rules; **not synonymous with commit**. |
| Commit | Completes the transaction and confirms changes synchronized validly with the database. |
| Detached entity | An entity no longer attached to a persistence context; changing its fields does not automatically generate an UPDATE. |

In a typical transaction-scoped JPA setup, the persistence context is managed per transaction. However, when Spring executes post-commit callbacks, the transaction manager's resource cleanup order may leave an `EntityManager` usable **for a brief window**. After the callback finishes and resources are cleaned up, do not assume the object remains managed.

Other configurations such as `OpenEntityManagerInView`, an extended persistence context, or an application-managed `EntityManager` have their own lifecycles. Do not infer from a single `em.contains(...) == true` that the entity will remain managed after the method returns.

## 3. Event ordering: from publishEvent to the AFTER_COMMIT callback

Suppose a service saves an order and publishes `OrderCreated` within a transaction:

~~~text
Transaction execution flow
  |
  | @Transactional createOrder()
  |    - EntityManager.persist(order)
  |    - publishEvent(new OrderCreated(orderId))
  |      => registers handling by transaction phase
  |
  | business method finishes
  v
Spring Transaction Manager
  |
  | flushes necessary data and COMMITS the main transaction
  |
  | invokes post-completion synchronization callbacks
  |    - @TransactionalEventListener(AFTER_COMMIT)
  |    - resources may still be bound to the thread
  |    - no further commit pass for new changes on the old tx
  |
  | cleans up/unbinds/closes resources of the main transaction
  v
returns control to the caller
~~~

A few points to get exact:

1. `@TransactionalEventListener` defaults to the `AFTER_COMMIT` phase. When there is no active transaction, the listener **is not executed** by default unless `fallbackExecution = true` is set.
2. Per the `TransactionPhase.AFTER_COMMIT` Javadoc, this is a specialization of **`AFTER_COMPLETION`**. It occurs in the transaction completion callback chain, **not the `TransactionSynchronization.afterCommit()` method itself**. Both are post-commit points, but API names and callback order must not be conflated.
3. `AFTER_COMMIT` is invoked only when the transaction completes successfully. On rollback, this listener does not run; `AFTER_ROLLBACK` can be used when you want to react to rollback.
4. In Spring using thread-bound transactions (`PlatformTransactionManager`), resources remaining bound during the callback is the exact situation the Javadoc warns about. Never treat it as a still-open write transaction.

## 4. Pitfall: modifying a managed entity after commit without changing database data

Consider the following listener snippet using the same persistence context still accessible at callback time:

~~~java
@PersistenceContext
private EntityManager entityManager;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    OrderEntity order = entityManager.find(OrderEntity.class, event.orderId());
    order.setStatus("NOTIFIED");
}
~~~

*This is illustrative code that must reside in a Spring bean with `OrderEntity` and `OrderCreated` defined; not a standalone program.*

The code may not throw an error right away: the entity is found, and `setStatus(...)` mutates the in-memory object. Yet **the old transaction has already committed**; dirty checking does not automatically create another commit pass. If a new transaction/persistence context is later opened to query the database, the stored value may still be the original one.

Three layers of state must be distinguished:

| Observation | What may be seen? | Does it prove committed? |
| --- | --- | --- |
| Reading the same Java object again | Sees `status = "NOTIFIED"` because the field was just assigned. | **No.** |
| `EntityManager.find(...)` in the same still-alive persistence context | May return the same managed instance from the first-level cache. | **No.** |
| Reading with a new transaction and persistence context after the callback has ended | Sees the data actually committed in the DB. | Suitable for verifying persistence, subject to isolation/cache settings. |

**Do not use `save(...)`, `saveAndFlush(...)`, or `entityManager.flush()` as a substitute for commit.** `flush` only synchronizes state to the database under suitable transactional conditions; calling it after a transaction finishes may fail to persist as expected or throw an error depending on the API/provider. It does not create a new commit for an already-closed transaction.

## 5. Practical Java 17+ example with Spring Boot, JPA, and H2

This example demonstrates two behaviors inside **the same `AFTER_COMMIT` listener**:

- The listener modifies a property of a managed entity in the old persistence context; the modified value **is not committed**.
- The listener calls another service using `REQUIRES_NEW` to write an audit row; the change in the **new transaction** commits independently.

### 5.1. Create a minimal application

Requires Java 17+, Maven, and access to Maven Central to download dependencies initially. Create the structure:

~~~text
after-commit-demo/
├── pom.xml
└── src/main/
    ├── java/demo/AfterCommitDemo.java
    └── resources/application.properties
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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

Contents of `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:aftercommit;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.root=ERROR
~~~

### 5.2. Complete source code

Contents of `src/main/java/demo/AfterCommitDemo.java`:

~~~java
package demo;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.Id;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.Table;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
public class AfterCommitDemo implements CommandLineRunner {

    private final OrderService orders;
    private final ReportService report;

    public AfterCommitDemo(OrderService orders, ReportService report) {
        this.orders = orders;
        this.report = report;
    }

    public static void main(String[] args) {
        SpringApplication.run(AfterCommitDemo.class, args);
    }

    @Override
    public void run(String... args) {
        orders.createOrder(42L);
        report.printDatabaseState(42L);
    }

    public record OrderCreated(long orderId) {}
}

@Entity
@Table(name = "demo_orders")
class DemoOrder {

    @Id
    private Long id;
    private String status;

    protected DemoOrder() {}

    public DemoOrder(long id, String status) {
        this.id = id;
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}

@Entity
@Table(name = "demo_audit")
class DemoAudit {

    @Id
    private Long id;
    private String action;

    protected DemoAudit() {}

    public DemoAudit(long id, String action) {
        this.id = id;
        this.action = action;
    }

    public String getAction() {
        return action;
    }
}

@Service
class OrderService {

    @PersistenceContext
    private EntityManager em;

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void createOrder(long id) {
        em.persist(new DemoOrder(id, "CREATED"));
        events.publishEvent(new AfterCommitDemo.OrderCreated(id));
        System.out.println("Service: published event " + id);
    }
}

@Component
class OrderCommittedListener {

    @PersistenceContext
    private EntityManager em;

    private final AuditService audits;

    public OrderCommittedListener(AuditService audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(AfterCommitDemo.OrderCreated event) {
        DemoOrder order = em.find(DemoOrder.class, event.orderId());
        System.out.println("Listener: managed=" + em.contains(order));

        order.setStatus("CHANGED_AFTER_COMMIT");
        System.out.println("Listener: memory=" + order.getStatus());

        audits.writeAudit(event.orderId());
    }
}

@Service
class AuditService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long id) {
        em.persist(new DemoAudit(id, "SAVED"));
        System.out.println("AuditService: wrote audit in new tx");
    }
}

@Service
class ReportService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public void printDatabaseState(long id) {
        DemoOrder order = em.find(DemoOrder.class, id);
        DemoAudit audit = em.find(DemoAudit.class, id);
        System.out.println("DB: order=" + order.getStatus());
        System.out.println("DB: audit=" + (audit == null ? "NONE" : audit.getAction()));
    }
}
~~~

The entity and service classes in the example are package-private classes in `demo`, declared in one file for easy copying. Entities have a `protected` no-arg constructor and are not `final`; only `AfterCommitDemo` is `public` so Java compiles cleanly matching the filename.

Run from the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Lines printed by the program itself to stdout in the illustrative configuration, excluding Maven/Hibernate logs:

~~~text
Service: published event 42
Listener: managed=true
Listener: memory=CHANGED_AFTER_COMMIT
AuditService: wrote audit in new tx
DB: order=CREATED
DB: audit=SAVED
~~~

### 5.3. Why does that output happen?

1. `OrderService.createOrder(...)` runs through the Spring `@Transactional` proxy, creates `DemoOrder(42, "CREATED")` in the main transaction's persistence context, and publishes the event. `@TransactionalEventListener` registers handling for after the transaction commits.
2. When the service method finishes, the transaction manager flushes necessary changes and commits the order row to H2.
3. At `AFTER_COMMIT`, following the normal JPA transaction manager flow, the `EntityManager` is still bound to the just-finished transaction. `em.find(...)` can retrieve the managed entity from the persistence context and `em.contains(order)` returns `true`.
4. `order.setStatus("CHANGED_AFTER_COMMIT")` only changes the in-memory object. Because the main commit has already completed, this change has no corresponding commit pass. That is the meaning of `Listener: memory=...`.
5. `AuditService.writeAudit(...)` is called through **another bean**, so the `@Transactional(propagation = REQUIRES_NEW)` proxy takes effect. Spring suspends the old resource, creates a new transaction for the `DemoAudit` row, and commits when the method exits normally.
6. `ReportService.printDatabaseState(...)` also runs through a proxied bean in a new read transaction with its own persistence context. It sees `order=CREATED` in the DB, while the audit row created in the new transaction has `action=SAVED`.

**Conclusion from the example:** `managed=true` describes the object's state in the persistence context at a point in time, **not proof that post-commit changes were saved**. Always verify through a new transaction/persistence context when checking whether data actually committed.

## 6. The right way to write data after commit: REQUIRES_NEW

When the requirement is "write an audit record only if creating the order committed successfully", move the write logic into an independent service:

~~~java
@Component
class OrderCreatedListener {

    private final AuditWriter auditWriter;

    OrderCreatedListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCreated(OrderCreated event) {
        auditWriter.record(event.orderId());
    }
}

@Service
class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(long orderId) {
        // Look up data in the new persistence context when needed.
        // Write audit/outbox to DB and commit the new transaction.
    }
}
~~~

*The snippet above only illustrates the bean-splitting pattern. `OrderCreated`, repository/`EntityManager` parts, and imports must be defined in a real application; the complete runnable example is in section 5.*

Why split into separate beans? In Spring's default proxy mechanism, if the listener calls `this.record(...)` on a `@Transactional(REQUIRES_NEW)` method **in the same object**, the internal call does not pass through the transaction proxy; the annotation may not create a new transaction as expected. Calling another Spring bean ensures the method is intercepted properly.

`Propagation.REQUIRES_NEW` requires an independent physical transaction; if a transaction is bound to the thread, Spring suspends and restores the old resource as supported by the transaction manager. This consumes additional connection resources; applications with high callback volume must watch connection pool sizing and transaction hold time.

`TransactionTemplate` with `REQUIRES_NEW` propagation can be used when defining transaction boundaries programmatically; both approaches aim to create a genuinely new commit for post-commit work.

## 7. Patterns that easily go wrong

### 7.1. Writing directly in AFTER_COMMIT and trusting save

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    OrderEntity order = repository.findById(event.orderId()).orElseThrow();
    order.setStatus("NOTIFIED");
    repository.save(order);
}
~~~

*This is a non-standalone illustrative snippet; it requires the corresponding entity, repository, and Spring bean.*

The `save` call may return normally without any additional commit on the old transaction. Move the write into a `REQUIRES_NEW` method on another bean, and reload the entity inside the new transaction's persistence context.

### 7.2. Adding default @Transactional thinking a new transaction was created

~~~java
@Transactional
public void markNotified(long id) {
    // Default propagation = REQUIRED.
}
~~~

If called while the old transaction resource is still bound, `REQUIRED` may "join" the just-committed context instead of creating the desired new commit boundary. Choose `REQUIRES_NEW` when the problem genuinely requires a separate DB operation after commit.

### 7.3. Passing a managed entity directly into the event

~~~java
events.publishEvent(new OrderCreatedEntity(order));
~~~

*`OrderCreatedEntity` is a hypothetical event type.*

After commit, the entity can become detached; if the callback runs on another thread or after the persistence context closes, unloaded lazy properties can cause `LazyInitializationException` with Hibernate. Instead, prefer putting **the ID and minimal immutable data** into the event and querying again in a new transaction when needed.

### 7.4. Assuming AFTER_COMMIT alone guarantees event delivery

If the process stops right after the DB commit but before the callback finishes processing, Spring Application Events has no built-in durable queue for replay. If audit logging, external integration, or message sending is mandatory and must not be lost, consider a transactional outbox, a reliable queue, and idempotent handling.

## 8. Distinguishing AFTER_COMMIT from other phases and @Async

| Mechanism | Timing | What can be expected? |
| --- | --- | --- |
| Synchronous `@EventListener` | Immediately when `publishEvent(...)` invokes the listener | If the publisher is in a transaction, the listener can work before commit and errors can affect the main transaction. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Before commit | Can prepare/modify data in the active transaction according to flush/commit policy. |
| `@TransactionalEventListener(AFTER_COMMIT)` | After successful commit, in the completion chain | Post-commit action; new DB writes must have an independent transaction. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | After rollback | Cleanup or failure notification; no old transaction exists to commit new changes. |
| `@TransactionalEventListener(AFTER_COMPLETION)` | After commit or rollback | Runs regardless of completion outcome; check business state if conditional action is needed. |
| `@Async` combined with listener | Can offload handler body to an executor thread | Does not automatically inherit the transaction or persistence context bound to the publishing thread; data and error handling must be designed separately. |

Note: a plain `@TransactionalEventListener(AFTER_COMMIT)` listener still runs synchronously in the completion callback chain on the event-publishing thread. **"After commit" describes timing, not "asynchronous execution".** Adding `@Async` changes thread boundaries, exception handling, and access to the original persistence context.

With Spring's reactive transactions (supported for transactional event listeners since 6.1), the transaction lives in the Reactor context rather than `ThreadLocal`. Guidance about thread-bound `EntityManager` in this article applies mainly to **synchronous JPA + `PlatformTransactionManager`**; do not apply it mechanically to reactive pipelines.

## 9. Practical rules and self-verification

1. **Define timing clearly:** if data must be modified **before commit** and share rollback, consider handling it in the main transaction or `BEFORE_COMMIT`; if only after successful commit, use `AFTER_COMMIT`.
2. **Use a new transaction for post-commit DB writes:** place logic in a separate bean with `REQUIRES_NEW` or an equivalent `TransactionTemplate`.
3. **Never check persistence via a managed entity:** values in RAM or the first-level cache may not reflect committed data. Verify with a fresh query suited to transactions and caching.
4. **Keep event payloads lean and safe:** prefer IDs, timestamps, and necessary immutable data; avoid relying on lazy relations from an old entity.
5. **Do not rely on cleanup order to keep a session alive:** callbacks may see resources still bound under current implementations, but applications should not assume they stay alive indefinitely.
6. **Recognize the lossy nature of in-process events:** mandatory work requires retries, idempotency, and durable storage.
7. **Test against a real DB:** with H2, PostgreSQL, or a test DB, verify state after the listener runs using a new transaction; do not rely solely on `setter` logs.

### Self-check questions

**Question 1.** In `AFTER_COMMIT`, does `em.contains(order) == true` prove `order.setStatus(...)` will be written to the DB?

**Answer:** No. A still-accessible managed entity does not create another commit pass. Changes made after the main transaction has committed do not commit automatically.

**Question 2.** Why might adding plain `@Transactional` without attributes to a DB-writing method fail to solve the issue?

**Answer:** The default propagation is `REQUIRED`, which can join the old transaction's resource still bound during the callback. You must explicitly request a new transaction and call through a Spring proxy.

**Question 3.** What is a safer way when an audit record must be written after commit?

**Answer:** Have the listener call an independent service with `@Transactional(propagation = REQUIRES_NEW)` or use a `TransactionTemplate` with equivalent propagation; verify by querying in a new transaction.

**Question 4.** Does `@TransactionalEventListener(AFTER_COMMIT)` automatically replay events if the JVM crashes?

**Answer:** No. Default in-process events have no durable delivery/retry mechanism; if delivery must be guaranteed, add an appropriate design.

## References

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener` invocation timing, `fallbackExecution`, and transaction phases.
- [Spring Framework Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): warning that transaction resources may still be accessible while changes are no longer committed.
- [Spring Framework Javadoc — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): relationship between `AFTER_COMMIT` and `AFTER_COMPLETION`.
- [Spring Framework Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): post-commit callbacks and `REQUIRES_NEW` guidance.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` and `REQUIRES_NEW`.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/8.0/userguide/html_single/): managed/detached entities, dirty checking, flush, and persistence context lifecycle.
