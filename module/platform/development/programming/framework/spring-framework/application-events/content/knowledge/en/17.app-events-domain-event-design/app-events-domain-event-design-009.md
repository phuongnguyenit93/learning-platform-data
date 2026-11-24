# Domain Events and Transaction Boundaries

In domain-driven design, a **domain event** is a fact meaningful to the business, such as `OrderPaid`, `BookingConfirmed`, or `StockReserved`. An event is typically published after an aggregate transitions state; however, "called `publishEvent(...)`" and "data changes have committed" are **two different milestones**. Understanding **transaction boundaries** helps prevent sending emails for orders that ultimately roll back, avoids unnecessarily stretching transactions, and guides choosing reliable event delivery mechanisms.

In Spring Framework, three mechanisms play distinct roles:

- `ApplicationEventPublisher.publishEvent(...)`: hands the event to the application's event-publishing mechanism; this method itself neither commits the database nor guarantees durable storage of the event.
- `@EventListener`: typically runs immediately when the event is published, synchronously on the calling thread when using the default `SimpleApplicationEventMulticaster` without async configuration.
- `@TransactionalEventListener`: binds event handling to a phase of the active transaction, defaulting to `AFTER_COMMIT`; publishing inside a transaction leads to processing only after the corresponding outcome occurs.

This lesson moves from aggregate boundaries to transactions, explains cases with and without transactions, provides a Java 17+ test example using Spring Test + JDBC/H2, and discusses when a transactional outbox is needed instead of in-memory callbacks.

## 1. What does a domain event express?

An event should be named after **a business occurrence that has happened from the domain's perspective**, usually in the past tense: `PaymentCaptured`, `OrderPlaced`, `ReservationCancelled`. It differs from a **command** like `CapturePayment`: a command requests work; an event describes a change or decision.

Example of an order transitioning from `CREATED` to `PAID`:

~~~text
Client --command PayOrder--> Order application service
                                  |
                                  +-- Check business preconditions
                                  +-- Aggregate transitions CREATED -> PAID
                                  +-- Write state to database
                                  +-- Publish OrderPaid(orderId)
                                  |
                                  +-- End transaction
                                           |
                                           +-- COMMIT
                                           |     +-- after-commit listener
                                           |
                                           +-- ROLLBACK
                                                 +-- skip after-commit effects
~~~

At the **domain** level, an aggregate can record `OrderPaid` right after transition rules are satisfied. At the **persistence** level, that change becomes durable only after commit. Therefore, if an event leads to external side effects (emails, APIs, brokers), the system must decide whether consumers act **within the transaction** or **after the transaction succeeds**.

Payload design should keep data minimal and stable:

~~~java
public record OrderPaid(
    String eventId,
    String orderId,
    long orderVersion
) { }
~~~

This is a standalone Java 17+ record. `eventId` can serve deduplication, `orderId` identifies the aggregate, and `orderVersion` helps consumers detect stale or out-of-order events. Avoid attaching a managed JPA entity or persistence context directly to events shared across modules, because after the transaction closes, lazy loading or mutable state can cause errors or confusion.

## 2. Business, aggregate, and database transaction boundaries

An **aggregate boundary** defines the state whose invariants must remain consistent when processing a command. A **database transaction boundary** is the scope of DB operations that commit or roll back together. These two boundaries are related but not identical: one transaction can modify multiple tables/aggregates; a long-running business process may span multiple transactions and distinct events.

Example within one transaction:

~~~java
@Transactional
public void payOrder(String orderId) {
    Order order = orderRepository.getRequired(orderId);
    order.markPaid();
    orderRepository.save(order);
    publisher.publishEvent(new OrderPaid(eventId(), orderId, order.version()));
}
~~~

**This is a design excerpt**, not a standalone Java file: `Order`, repository, `eventId()`, and beans must be defined by the application. With JPA, `save()` may not flush SQL immediately; even if flushed, **flush is not commit**.

If Spring's transaction interceptor creates a transaction around `payOrder`, publishing occurs **inside the transaction**. A synchronous `@EventListener` runs right when `publishEvent` executes while the transaction is still open; a `@TransactionalEventListener(AFTER_COMMIT)` registers to wait until commit actually succeeds. If an exception triggers a rollback, the after-commit callback does not execute.

Note that `@Transactional` in default proxy mode requires calls to pass **through the Spring proxy**. Self-invoking `this.payOrder(...)` from the same bean can bypass the interceptor, leaving no transaction created as expected.

### Three milestones you must not conflate

| Milestone | What has happened | What is not yet certain |
| --- | --- | --- |
| Aggregate changes state | Domain rules permitted the state transition in memory | SQL flush, commit, durable persistence |
| `publishEvent(new OrderPaid(...))` returns | The publish call completed according to current multicaster configuration | Successful commit; async listener completion; durable delivery |
| Database commit succeeds | Changes in the transaction are finalized | Email/Kafka delivery succeeded; consumer processed exactly once |

"Publish after `save()`" **does not mean** "publish after commit." If business rules require calling external systems after data is finalized, use a mechanism tied to the **transaction outcome**, not just reordering two lines of code.

## 3. Synchronous listeners can extend the transaction

By default Spring uses the synchronous `SimpleApplicationEventMulticaster`. Example:

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    inventoryRepository.reserveFor(event.orderId());
}
~~~

This is an excerpt inside a Spring bean. If the service publishes the event inside a transaction and the listener calls a repository on the same thread/transaction, the reserve operation can participate in the **open transaction**. That can be useful when both changes must commit or roll back together.

However, distinguish **synchronous execution** from **mandatory business coupling**:

- If failing to reserve inventory means order payment must not complete, an explicit service call or handling within the same aggregate/application service may be clearer than a hidden listener.
- If a listener only updates metrics or sends a secondary email, letting its failure roll back the main business operation creates unnecessary coupling.
- A synchronous listener making HTTP calls, sending emails, or publishing to a broker before commit can create external side effects that **cannot be rolled back** with the database.

Risk example:

~~~text
BEGIN DB TRANSACTION
  UPDATE orders SET status='PAID' ...
  publish OrderPaid
      -> @EventListener sends "Payment succeeded" email
  INSERT audit ...  -- hits constraint error
ROLLBACK
Result: DB has no PAID order, customer already received email.
~~~

If a listener throws an exception, under the default synchronous multicaster with no error handler swallowing exceptions, the error can propagate back to the publisher and roll back the transaction per Spring rules. When `@Async` or an executor is enabled, listener exceptions may not return to the source transaction; do not infer retry guarantees or atomicity from that.

## 4. @TransactionalEventListener binds handling to transaction outcomes

Spring provides `@TransactionalEventListener` so listeners execute at a specific transaction phase:

| TransactionPhase | When the listener runs | Appropriate use cases |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit completes; transaction can still fail | Preparation/checks that belong inside the commit lifecycle |
| `AFTER_COMMIT` (**default**) | After successful commit | Sending notifications, signaling other systems when durable delivery guarantees are not required |
| `AFTER_ROLLBACK` | When the transaction rolls back | Recording failures or logical cleanup based on rollback outcome |
| `AFTER_COMPLETION` | After completion, whether commit or rollback | General cleanup, lifecycle tracking |

Example sending a receipt only after order state is committed:

~~~java
@Component
class ReceiptListener {

    private final ReceiptGateway gateway;

    ReceiptListener(ReceiptGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        gateway.sendReceipt(event.orderId());
    }
}
~~~

This is an excerpt; `ReceiptGateway`, `OrderPaid`, and imports for `@Component`, `@TransactionalEventListener`, and `TransactionPhase` must be defined. If the transaction rolls back, this listener is not invoked for that event. If the transaction commits, the callback executes, yet a gateway failure **does not automatically roll back the committed DB**. Thus after-commit addresses **timing**, not guaranteed delivery success.

If no suitable transaction exists when publishing, `@TransactionalEventListener` **does not run by default**. Setting `fallbackExecution = true` allows execution even without a transaction, but must be used intentionally: if the business requirement is "send only after commit," enabling fallback can break that contract.

### Database access inside post-commit listeners

After commit, transaction resources can **still remain bound to the thread** for a period even though the transaction has completed. If a post-commit callback writes more data to a repository without a new transaction, you cannot assume a second commit will occur for those changes.

If an after-commit listener needs to persist audit rows or durable delivery state, invoke a service starting a new transaction with `@Transactional(propagation = Propagation.REQUIRES_NEW)` through a Spring proxy, or use a `TransactionTemplate` configured with `PROPAGATION_REQUIRES_NEW`. Verify with a DB readback after the callback; do not assume a repository `save()` commits automatically.

## 5. Separating domain events from integration events

A **domain event** describes what happened in the application's business model. An **integration event** is a message published across module/service/process boundaries; it requires an evolvable versioned data contract and its own delivery, retry, and deduplication rules.

Example:

~~~text
Within domain/application:
  OrderPaid(eventId, orderId, version)
  --> internal listener updates read model

When publishing to external systems:
  PaymentSettledV1 {
    eventId,
    orderId,
    occurredAt,
    schemaVersion
  }
  --> transactional outbox / publisher --> Kafka/RabbitMQ/HTTP
~~~

This is a diagram, not complete JSON. Do not use persistence entity types or internal `TransactionContext` as cross-network message contracts. When externalizing events, consider exposed fields, access control, schema evolution, key-based ordering (e.g., `orderId`), and idempotency.

A domain event published in memory is only an **internal notification**. It does not survive a process crash on its own. Hence the difference between an after-commit listener and an outbox is the **durability of the intent to send**.

## 6. Java 17+ integration example: real transactions, commit, and rollback

The example below uses Spring Framework, Spring JDBC, in-memory H2, and JUnit 5. It verifies:

1. The service updates the DB and publishes `PaymentCaptured` within the same JDBC transaction.
2. A synchronous `@EventListener` observes the uncommitted `CAPTURED` state inside **the same transaction**.
3. The `AFTER_COMMIT` listener records a marker only after commit.
4. On rollback, the DB reverts to `CREATED`; the `AFTER_COMMIT` callback does not run, while `AFTER_ROLLBACK` does.
5. When published outside a transaction, the regular listener still runs, whereas transactional listeners do not run by default.

### 6.1. Gradle dependencies

`build.gradle` file using Java 17 and minimal test dependencies:

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

Spring Boot projects should prefer the Boot BOM in use and avoid forcing individual Spring Framework versions if incompatible with that BOM.

### 6.2. File src/test/java/example/events/DomainEventTransactionTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(DomainEventTransactionTest.Config.class)
class DomainEventTransactionTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired PaymentService service;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired Trace trace;

    @BeforeEach
    void setUp() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS payment (" +
            "id VARCHAR(40) PRIMARY KEY, " +
            "state VARCHAR(20) NOT NULL)"
        );
        jdbc.update("DELETE FROM payment");
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "A-1", "CREATED"
        );
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "B-2", "CREATED"
        );
        jdbc.update(
            "INSERT INTO payment(id, state) VALUES (?, ?)",
            "C-3", "CREATED"
        );
        trace.clear();
    }

    @Test
    void commitDeliversAfterCommitEvent() {
        service.capture("A-1", false);

        assertEquals("CAPTURED", state("A-1"));
        assertEquals(
            List.of(
                "inside:A-1:CAPTURED",
                "committed:A-1"
            ),
            trace.snapshot()
        );
    }

    @Test
    void rollbackDoesNotDeliverAfterCommitEvent() {
        service.capture("B-2", true);

        assertEquals("CREATED", state("B-2"));
        assertEquals(
            List.of(
                "inside:B-2:CAPTURED",
                "rolledBack:B-2"
            ),
            trace.snapshot()
        );
    }

    @Test
    void withoutTransactionOnlyNormalListenerRuns() {
        publisher.publishEvent(new PaymentCaptured("C-3"));

        assertEquals("CREATED", state("C-3"));
        assertEquals(
            List.of("inside:C-3:CREATED"),
            trace.snapshot()
        );
    }

    private String state(String id) {
        return jdbc.queryForObject(
            "SELECT state FROM payment WHERE id = ?",
            String.class,
            id
        );
    }

    record PaymentCaptured(String orderId) { }

    static class Trace {
        private final List<String> values = new ArrayList<>();

        void add(String value) {
            values.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        void clear() {
            values.clear();
        }
    }

    static class PaymentService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        PaymentService(JdbcTemplate jdbc, TransactionTemplate tx,
                       ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        void capture(String id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "UPDATE payment SET state = ? WHERE id = ?",
                    "CAPTURED", id
                );
                publisher.publishEvent(new PaymentCaptured(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    static class PaymentListeners {
        private final JdbcTemplate jdbc;
        private final Trace trace;

        PaymentListeners(JdbcTemplate jdbc, Trace trace) {
            this.jdbc = jdbc;
            this.trace = trace;
        }

        @EventListener
        public void onPublication(PaymentCaptured event) {
            String current = jdbc.queryForObject(
                "SELECT state FROM payment WHERE id = ?",
                String.class,
                event.orderId()
            );
            trace.add(
                "inside:" + event.orderId() + ":" + current
            );
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(PaymentCaptured event) {
            trace.add("committed:" + event.orderId());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(PaymentCaptured event) {
            trace.add("rolledBack:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:domain_event_tx;DB_CLOSE_DELAY=-1",
                "sa",
                ""
            );
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

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        PaymentService paymentService(JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new PaymentService(jdbc, tx, publisher);
        }

        @Bean
        PaymentListeners paymentListeners(JdbcTemplate jdbc, Trace trace) {
            return new PaymentListeners(jdbc, trace);
        }
    }
}
~~~

Run from a project with the Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.DomainEventTransactionTest"
~~~

On Windows PowerShell you can use `./gradlew.bat` instead of `./gradlew`. With matching dependencies and test setup, all three tests **PASS**. They do not print `inside:`, `committed:`, or `rolledBack:` lines to stdout; those strings are recorded into `Trace` and checked via assertions.

**What the test proves:** `PaymentService` opens a transaction via `TransactionTemplate`, writes to the DB, and publishes within the same scope; the regular listener uses `JdbcTemplate` on the same thread and reads the uncommitted value; the `AFTER_COMMIT` listener records only when commit succeeds; on rollback, the rollback-phase callback runs and the DB reverts to its initial state.

If you tried replacing `AFTER_COMMIT` with a regular `@EventListener` to send real notifications, the notification would fire even in the rollback test. That is why critical external side effects must not sit inside a synchronous listener if business rules require commit first.

### 6.3. Why not put @Transactional on the test itself?

In Spring TestContext, a `@Transactional` test is typically **rolled back automatically** after the test method. Relying solely on that test transaction means `AFTER_COMMIT` callbacks never get a chance to run before assertions inside the method. The example uses `TransactionTemplate` in a non-transactional test to explicitly end commit/rollback inside the service call.

If you must use a test-managed transaction, you can use `TestTransaction.flagForCommit()` followed by `TestTransaction.end()` where appropriate. With JPA/Hibernate, also consider `flush` timing and DB constraints; do not confuse a modified persistence context with committed data.

## 7. Post-commit failures: why in-process events are not durable enough

`@TransactionalEventListener(AFTER_COMMIT)` avoids processing when a transaction rolls back. Yet there is a **post-commit gap**:

~~~text
T0: UPDATE order
T1: COMMIT succeeds
T2: JVM/process suddenly stops
T3: AFTER_COMMIT listener has not yet called broker/email
=> DB changed, but notification may be lost.
~~~

Even if the listener runs, the broker or external system may encounter network failures; retries can send multiple times. Thus `AFTER_COMMIT` is a timing condition, not an exactly-once delivery contract. When notifications are auxiliary, you can accept the risk alongside appropriate logging/retries. When an event must definitely be delivered, persist the **intent to publish** durably.

### Transactional outbox

A common pattern is writing **business data and an outbox record in the same database transaction**:

~~~sql
BEGIN;

UPDATE orders
SET state = 'PAID'
WHERE id = 'O-42';

INSERT INTO outbox(event_id, aggregate_id, event_type,
                   payload, delivery_state)
VALUES ('E-42', 'O-42', 'OrderPaid',
        '{"orderId":"O-42"}', 'PENDING');

COMMIT;
~~~

This SQL is **a conceptual illustration**; you need a real schema, identifier columns, and proper error handling before running in production. If the transaction rolls back, both the update and the outbox insert roll back. A separate worker reads committed outbox records, publishes to the broker, marks results, and retries on failure. Since a record may be sent again, consumers must handle idempotently, typically by `eventId`.

~~~text
Business transaction:
  UPDATE order + INSERT outbox  -- atomic commit

Publisher worker:
  read committed outbox
  -> send broker with retry
  -> mark delivered

Consumer:
  deduplicate by eventId
  -> apply business side effect
~~~

An outbox solves the risk of "DB committed without recording the intent to send." It **does not automatically guarantee end-to-end exactly-once delivery**, nor global ordering across all aggregates. If per-`orderId` ordering is needed, choose partition keys and processing mechanisms that preserve ordering per key.

### Spring Modulith Event Publication Registry

When a system consists of multiple application modules inside one Spring application, **Spring Modulith** provides a mechanism that records application events dispatched to transactional listeners in a publication registry. The registry can store publication records within the source transaction, mark them complete when listeners finish, and help locate/resubmit incomplete publications according to the chosen mechanism and configuration.

This is a specific add-on from **Spring Modulith**, **not a Spring Framework default**. It requires matching dependencies, persistence integration, and configuration. Nor should you equate every Modulith externalization option with a full broker-backed transactional outbox; verify the delivery guarantees of the adapter in use.

## 8. Choosing a design based on transaction requirements

| Scenario | Design suggestion | What to test |
| --- | --- | --- |
| Same-aggregate invariants must hold | Handle directly in the aggregate/application service in the same transaction | Domain rules + rollback on violation |
| Listener updates related data and must commit/roll back together | Synchronous listener in the same transaction, if there is a clear modular reason | Listener joins transaction, failure policy |
| Send email after payment commits; rare crash risk acceptable | `@TransactionalEventListener(AFTER_COMMIT)` | Commit sends, rollback skips; gateway failures observed |
| Must never lose intent to deliver event | Transactional outbox or registry with suitable recovery | Crashes at various points, retries, idempotency, ordering key |
| Listener creates a new record after commit | Open a separate transaction (`REQUIRES_NEW`) | Record commits independently and is readable after callback |
| Two operations in two microservices | Separate transactions per service + integration events and eventual consistency | Final state, duplicate messages, transient failures |
| Reactive transactions with R2DBC | Carry event in Reactor subscriber context; use `TransactionalEventPublisher` | Commit/rollback with `ReactiveTransactionManager` |

Specifically, **`@Order` does not create a transaction boundary**. Listener invocation order does not replace commit, create locks, or enlist emails into DB transactions. Likewise, `@Async` runs listeners on another thread and does not propagate the original thread's transaction context.

With reactive transactions, Spring Framework 6.1+ supports `@TransactionalEventListener` when the event source carries `TransactionContext`; `TransactionalEventPublisher` is the helper that attaches context from a Reactor chain. Do not directly apply the thread-bound JDBC assumptions above to an R2DBC pipeline.

## 9. Common design mistakes

**1. Publishing a domain event and assuming data has committed.** Events can be created and published inside an unfinished transaction. Specify which consumers may run before commit and which must wait for the transaction outcome.

**2. Using listeners to hide mandatory business steps.** If "A must succeed before B" is an invariant, an explicit service call or aggregate operation is easier to understand and debug than a chain of listeners invisible at the call site.

**3. Sending synchronous emails or HTTP requests before commit.** Rollback only undoes changes inside the transaction, not external requests already sent. Move side effects to after-commit when suitable; use an outbox if notifications cannot be lost.

**4. Enabling `fallbackExecution = true` without checking requirements.** Transactional listeners can then run outside any transaction, breaking the "only after commit" meaning for some calls.

**5. Writing to the DB inside `AFTER_COMMIT` without opening a new transaction.** This can touch stale post-commit transaction resources without committing again. Open a new transaction using `REQUIRES_NEW` and test readback.

**6. Putting mutable JPA entities in event payloads and processing later.** After the transaction, entities may be detached; lazy fields fail, and objects may differ from state at publish time. Use immutable DTOs/records containing IDs and needed values.

**7. Mistaking `@Async` for durability.** Async listeners can lose tasks when a process crashes; exceptions do not necessarily propagate back to the publisher. Use retries/idempotency, a registry, or an outbox if delivery is required.

**8. Writing an integration test with `@Transactional` and expecting `AFTER_COMMIT` to fire immediately.** TestContext usually rolls back test transactions at the end of tests. Explicitly commit with `TransactionTemplate` or `TestTransaction` when testing after-commit callbacks.

**9. Propagating an event to multiple systems without IDs/versions.** Retries often produce duplicates; consumers need idempotency keys and, where necessary, version/sequence data to handle out-of-order updates.

## 10. Self-check questions

**Question 1:** If a service calls `repository.save(order)` and then `publishEvent(new OrderPaid(...))` inside `@Transactional`, is the event guaranteed to be durable?

No. The DB row may not be flushed yet and the transaction can still roll back; calling `ApplicationEventPublisher` does not mean a commit occurred or the event was durably stored.

**Question 2:** When should you use a synchronous `@EventListener` versus `@TransactionalEventListener`?

Use a synchronous listener when work needs to run inside the event-publishing flow and can share the caller's transaction. Use a transactional listener when handling must depend on commit/rollback outcomes, especially for post-commit side effects.

**Question 3:** Why does an `AFTER_COMMIT` listener not guarantee an email reaches the customer?

Because the callback may not run if the process crashes after commit, and the gateway itself can fail. It only ties execution timing to commit, without providing a durable queue or full retry mechanism.

**Question 4:** What does an outbox guarantee, and what else is needed?

It allows persisting business state and the intent to send an event **atomically** in the same DB transaction. You still need a delivery worker, retries, duplicate/idempotency handling, and ordering as required.

**Question 5:** If an event is published outside a transaction, does `@TransactionalEventListener` run by default?

No. There is no suitable transaction to register a callback against; only enabling `fallbackExecution = true` triggers a fallback path with different semantics.

**Key takeaway:** domain events and transaction boundaries must be designed together. **Aggregate state transition**, **event publication**, **database commit**, and **consumer side effects** are independent milestones. Choose synchronous listeners, transaction-phase listeners, or an outbox based on consistency and delivery requirements, and test commit, rollback, and post-commit failure paths.

## References

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Application Events and synchronous dispatch defaults](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework – TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Modulith – Working with Application Events and the Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
