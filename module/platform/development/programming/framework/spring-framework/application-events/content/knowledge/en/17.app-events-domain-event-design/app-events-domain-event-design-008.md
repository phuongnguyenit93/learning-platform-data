# Publishing Events in Application Services in Domain Event Design (Spring Framework)

## 1. Purpose

An application service is the orchestration point for a use case in an application: it receives a command, validates application boundaries, loads or creates an aggregate, asks the domain model to execute behavior, persists state, and reflects **business events that have occurred**. One way to reflect outcomes without coupling directly to every downstream task is to publish a **domain event**.

For example, after an order transitions to `SUBMITTED`, the application service can publish an **OrderSubmitted** event. Other listeners can write audit logs, update caches, generate notifications, or trigger integration workflows. As a result, the service does not have to invoke each auxiliary component directly, reducing coupling.

However, three things must never be conflated:

1. **The business event has been created:** the domain model or application service has confirmed a fact.
2. **The event has been published:** the application service invoked ApplicationEventPublisher.publishEvent.
3. **The database has committed and subscribers succeeded:** these are separate milestones; publishEvent does not automatically guarantee either of them.

This lesson focuses on where to publish, transactions, listener types, rollback handling, durability, idempotency, and a complete Java 17+ example.

## 2. Responsibility boundaries of an application service

A typical flow:

~~~text
Controller / Message handler
      |
      v
OrderApplicationService.submit(command)
      |
      +-- validate input, check permissions
      +-- load/create Order aggregate
      +-- order.submit()          [domain invariant]
      +-- repository.save(order)  [change within transaction]
      +-- publish(OrderSubmitted)
      |
      +-- transaction commit or rollback
                |
                +-- AFTER_COMMIT listeners
~~~

The **domain model** decides whether state can transition from DRAFT to SUBMITTED; the **application service** coordinates repositories, transactions, and publishing notifications to other components. Tasks such as sending emails, updating indexes, or calling partner APIs typically do not belong to the aggregate's core invariants.

This is one way to organize code, not a mandatory rule for every codebase. In a rich domain model, the aggregate can record an internal list of domain events; the application service collects and publishes them after valid state transitions. **Recording** events inside the aggregate differs from **publishing** via a framework adapter.

A domain event should describe an occurrence in the past tense: OrderSubmitted, PaymentCaptured, AccountRegistered. Names like SendEmail or UpdateCache are usually commands requesting an action rather than domain facts.

### What should an event payload carry?

Java 17 allows using records:

~~~java
// Illustrative snippet; requires importing java.time.Instant.
public record OrderSubmitted(
        String eventId,
        long orderId,
        Instant occurredAt,
        String customerId
) {}
~~~

| Field | Purpose |
| --- | --- |
| eventId | Identifies the event for tracing, idempotency, and detecting duplicate processing |
| orderId | Aggregate key, allowing subscribers to fetch data when needed |
| occurredAt | Timestamp when the business fact occurred, not necessarily when a subscriber processes it |
| customerId | Business data subscribers genuinely need, not the entire JPA entity |

Prefer IDs or immutable snapshots, and do not publish raw managed/lazy JPA objects. Do not put passwords, tokens, or unnecessary sensitive data into events. Records provide shallow immutability: if a record holds a mutable list, recipients can still mutate the contents inside.

For events crossing into other services, you must also consider schemaVersion, eventType, tenant/correlation IDs, backward compatibility, and sensitive-data controls.

## 3. Spring Application Events mechanism

Spring provides the **ApplicationEventPublisher** interface. A Spring bean can inject this interface via constructor and call:

~~~java
// Illustration inside a Spring-managed application service.
publisher.publishEvent(new OrderSubmitted(
        UUID.randomUUID().toString(),
        order.getId(),
        Instant.now(),
        order.getCustomerId()
));
~~~

Spring accepts plain POJOs/records as events; subclassing ApplicationEvent is not required. The publishEvent method returns **void**—it does not return a Future, durable acknowledgment, or broker receipt.

The ApplicationEventMulticaster selects listeners interested in the event type. With the default SimpleApplicationEventMulticaster, regular listeners are invoked **synchronously on the publishing thread**. If a listener does not catch a RuntimeException, it can propagate up to the publisher; when the publisher is inside a transaction, the exception can even roll back the use case.

Two common ways to listen are:

~~~java
// Illustration inside a Spring bean: invoked immediately upon default publish.
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    log.info("Order submitted: {}", event.orderId());
}
~~~

~~~java
// Illustration inside a Spring bean: waits for transaction COMMIT.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderSubmitted event) {
    notificationGateway.sendOrderSubmitted(event.orderId());
}
~~~

A **regular EventListener** runs immediately during publication under the default configuration. **TransactionalEventListener** registers a callback on the transaction and waits for the chosen phase. AFTER_COMMIT is the default phase; other phases are BEFORE_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION.

A regular listener suits fast internal calculations that should run right in the flow. An AFTER_COMMIT listener suits cases where side effects must not start if the transaction rolls back. However, AFTER_COMMIT is still only an in-process callback, not a durable delivery mechanism.

## 4. Placing publishEvent at the right spot in a use case

The key point is: **publish while the business transaction is active**, after domain behavior succeeds and changes have been requested to persist. The transactional listener callback itself will wait for commit.

A service annotated with @Transactional can be written as:

~~~java
// ILLUSTRATIVE SNIPPET: OrderRepository, Order, and command are not defined here.
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void submit(SubmitOrderCommand command) {
        Order order = repository.findById(command.orderId())
                .orElseThrow();
        order.submit();                     // domain invariant
        repository.save(order);             // persist changes
        publisher.publishEvent(new OrderSubmitted(
                UUID.randomUUID().toString(),
                order.getId(),
                Instant.now(),
                order.getCustomerId()
        ));
    }
}
~~~

This is an illustrative code snippet requiring matching imports and domain classes, not a standalone compilable file.

Calls must pass through the **Spring transaction proxy** for @Transactional to apply in proxy mode. When the submit method returns, the transaction interceptor still has to execute the commit. Thus **repository.save does not mean the commit is done**; an event published inside the method body is still emitted **before the actual commit**.

### A common mistake

~~~java
// Illustrates the wrong way if you want TransactionalEventListener to see the transaction:
orderService.submit(command); // this method commits itself before returning
publisher.publishEvent(new OrderSubmitted(...)); // outside any transaction
~~~

If there is no outer transaction, no transaction exists when publishEvent is called. By default TransactionalEventListener **is not invoked** because there is no context to register synchronization against.

The right pattern is not "publish after the @Transactional method returns," but "**publish inside the transaction**, so AFTER_COMMIT listeners trigger **after commit**."

### Why not publish from every layer?

- **Controller:** usually just coordinates request/response; publishing after the service already committed loses transaction context and puts domain decisions in the wrong layer.
- **Repository:** responsible for persistence; automatically publishing events on every save easily produces duplicate events or confuses saving with a business transition.
- **Plain aggregate:** can record events without depending on Spring; letting an adapter/application service publish keeps the domain model more independent.
- **Application service:** understands the use case and transaction boundary, making it a natural place to decide when to publish events upon valid completion.

If an architecture uses Spring Data domain events or a unit-of-work adapter, the mechanism may differ; you must still ensure events genuinely represent business facts and maintain consistent transaction boundaries.

## 5. Complete Java 17+ example: commit and rollback

This example runs with Spring Framework 6.2.12, Spring JDBC, in-memory H2, and Maven, **without Spring Boot**. It uses TransactionTemplate to make the full transaction boundary explicit. The service INSERTs an order and then publishes OrderSubmitted. Next, the service either lets the transaction commit or marks it rollback-only.

Three listeners record observations into an in-memory list:

- **@EventListener:** appends now:ID immediately upon publication.
- **@TransactionalEventListener(AFTER_COMMIT):** appends commit:ID only upon successful commit.
- **@TransactionalEventListener(AFTER_ROLLBACK):** appends rollback:ID upon rollback.

No listener writes back to the database after commit, so the example isolates event semantics from post-transaction data-access hazards.

Create directory:

~~~text
domain-event-service/
├── pom.xml
└── src/main/java/demo/DomainEventFromServiceDemo.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>domain-event-service</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. src/main/java/demo/DomainEventFromServiceDemo.java

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class DomainEventFromServiceDemo {

    public record OrderSubmitted(
            String eventId,
            long orderId,
            Instant occurredAt) {}

    public static final class EventTrace {
        private final List<String> history = new CopyOnWriteArrayList<>();

        public void add(String value) {
            history.add(value);
        }

        public String snapshot() {
            return String.join(" > ", history);
        }
    }

    public static final class OrderApplicationService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public OrderApplicationService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        public void submit(long id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO purchase_orders(id, state) VALUES (?, ?)",
                    id, "SUBMITTED");

                // Publish inside the transaction, before actual commit.
                publisher.publishEvent(new OrderSubmitted(
                    UUID.randomUUID().toString(), id, Instant.now()));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    public static final class OrderListeners {
        private final EventTrace trace;

        public OrderListeners(EventTrace trace) {
            this.trace = trace;
        }

        @EventListener
        public void immediately(OrderSubmitted event) {
            trace.add("now:" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderSubmitted event) {
            trace.add("commit:" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderSubmitted event) {
            trace.add("rollback:" + event.orderId());
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:domain_service;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager txManager) {
            return new TransactionTemplate(txManager);
        }

        @Bean
        public EventTrace eventTrace() {
            return new EventTrace();
        }

        @Bean
        public OrderApplicationService orderApplicationService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new OrderApplicationService(jdbc, tx, publisher);
        }

        @Bean
        public OrderListeners orderListeners(EventTrace trace) {
            return new OrderListeners(trace);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            EventTrace trace = context.getBean(EventTrace.class);
            OrderApplicationService service =
                    context.getBean(OrderApplicationService.class);

            jdbc.execute("""
                CREATE TABLE purchase_orders (
                    id BIGINT PRIMARY KEY,
                    state VARCHAR(20) NOT NULL
                )
                """);

            service.submit(1L, false);
            int one = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = 1",
                Integer.class);
            System.out.println(
                "after-commit db=" + one + " trace=" + trace.snapshot());

            service.submit(2L, true);
            int two = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = 2",
                Integer.class);
            System.out.println(
                "after-rollback db=" + two + " trace=" + trace.snapshot());
        }
    }
}
~~~

Run in the directory containing pom.xml with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DomainEventFromServiceDemo
~~~

Two lines printed by the program itself:

~~~text
after-commit db=1 trace=now:1 > commit:1
after-rollback db=0 trace=now:1 > commit:1 > now:2 > rollback:2
~~~

Even if libraries or Maven print extra logs, only those two lines are printed by the program code above. UUID and Instant are generated for event metadata without being printed, so predictable stdout does not depend on time or randomness.

### 5.3. Explaining the commit branch

1. TransactionTemplate opens a JDBC transaction.
2. The service INSERTs order 1, not yet committed.
3. The service calls publishEvent with OrderSubmitted.
4. The regular listener records now:1 immediately.
5. The AFTER_COMMIT listener registers synchronization with the active transaction.
6. The TransactionTemplate lambda finishes, and the transaction manager commits successfully.
7. Spring triggers the AFTER_COMMIT listener; trace appends commit:1.
8. Querying after the service returns yields db=1.

### 5.4. Explaining the rollback branch

1. The second transaction INSERTs order 2.
2. The service publishes the event, and the regular listener appends now:2.
3. status.setRollbackOnly marks the transaction for rollback.
4. The transaction manager rolls back; the AFTER_COMMIT listener does not run.
5. The AFTER_ROLLBACK listener appends rollback:2.
6. Querying after the transaction yields db=0, yet now:2 stays in the list because this in-memory mutation **is not part of the JDBC transaction**.

This is why you must not execute irreversible side effects such as sending emails or calling payment APIs inside a regular listener if they are only allowed after the database commits.

## 6. Four phases when synchronizing with transactions

| TransactionPhase | Meaning | Suitable scenario |
| --- | --- | --- |
| BEFORE_COMMIT | Listener runs before actual commit | Data checks and preparation; rollback is still possible |
| AFTER_COMMIT | Listener runs only if commit succeeds | Notifications or workflows that must start only after commit |
| AFTER_ROLLBACK | Listener runs if the transaction rolls back | Cleaning up temporary resources and observing failures |
| AFTER_COMPLETION | Listener runs when the transaction finishes, whether commit or rollback | General cleanup and metrics |

AFTER_COMMIT on TransactionalEventListener is a special case during the afterCompletion phase when the status is committed; it is not completely identical to the TransactionSynchronization.afterCommit() hook. Do not design ordering between different hooks by guessing from their names.

When an event is published **outside a transaction**, transactional listeners do not handle it by default; fallbackExecution=true enables immediate execution on a fallback path. That is an intentional behavior change, not a fix for a missing transaction boundary.

## 7. Failure boundaries and situations to avoid

### 7.1. Publishing inside a transaction vs publishing after commit

Inside a @Transactional method, publishEvent executes before the transaction interceptor completes the commit. Without an outer transaction, placing publishEvent **after calling a service that already committed** leaves TransactionalEventListener with no transaction to track.

With PROPAGATION_REQUIRED, a child service can join the outer transaction; AFTER_COMMIT callbacks wait until the outermost physical transaction commits. With REQUIRES_NEW, the inner transaction commits separately, so events may be handled right after the inner commit even if the outer transaction later rolls back.

### 7.2. Do not write new data directly after commit without a new transaction

Per Spring Framework, AFTER_COMMIT callbacks happen after the transaction has committed, yet old resources like the JDBC Connection may still be bound while the callback runs. Data-access calls at this moment may participate in that resource **without another commit happening**.

To persist an audit record in an independent transaction after commit, call another Spring service through a proxy with:

~~~java
// Illustration, not a standalone program.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(String eventId) {
    auditRepository.save(new AuditRecord(eventId));
}
~~~

If audit or outbox records must be persisted atomically with the order, INSERT them directly **inside the original transaction** instead of waiting for a post-commit listener.

### 7.3. Exceptions and async

- A synchronous regular listener can throw an exception back to the publisher, causing rollback under the current transaction rules.
- An AFTER_COMMIT listener can fail **after the DB has already committed**. Callback errors cannot reverse the old transaction; you need logs, metrics, retries, or compensating workflows.
- An @Async listener can run on another thread; publishEvent returning does not mean background work finished, and @Order does not guarantee completion order when running concurrently.
- PlatformTransactionManager transactions are typically thread-bound. If publishing is handed off to a task executor with no transaction on the new thread, transactional listeners may be skipped.
- With ReactiveTransactionManager, context lives in the Reactor Context; Spring 6.1+ supports transactional events when the context is properly attached to the event, e.g., via TransactionalEventPublisher.

Do not treat publishEvent as a broker with built-in acknowledgments, replay, or retries.

## 8. When to use a transactional outbox?

TransactionalEventListener(AFTER_COMMIT) only solves **timing**, not **durability**. Crash scenario:

~~~text
BEGIN transaction
  INSERT purchase_orders
COMMIT
[process crashes before sending to broker]
database has the order, but the message may never have been sent
~~~

To avoid losing the intent to publish an integration event, use a **transactional outbox**:

1. In the same business transaction, write the order data.
2. INSERT an outbox record containing eventId, aggregateId, eventType, payload, and createdAt.
3. Commit together: the order and outbox either exist together or roll back together.
4. A relay/worker reads outbox rows in batches, sends them to the broker, and marks them processed.
5. On send errors, retry; use eventId and consumer idempotency to mitigate duplicate effects.
6. Monitor backlog, dead letters, and operational states.

Minimalist schema example (illustrative SQL; adjust for your actual DBMS):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(50) PRIMARY KEY,
    aggregate_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json CLOB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP
);
~~~

Important: the outbox row must be created **before commit inside the application service's transaction**. Do not move outbox insertion into an AFTER_COMMIT listener and assume it remains atomic with the main transaction.

You can use an after-commit callback to wake up the relay and reduce latency, but the relay must still poll the outbox periodically because wake-up callbacks can be lost on a process crash.

An outbox does not automatically yield end-to-end exactly-once delivery; brokers can redeliver and relays can retry after sending but before marking complete, so consumers need idempotency/deduplication.

## 9. Domain events differ from integration events

**Domain events** describe facts within the current bounded context; in-process distribution via Spring may be sufficient.

**Integration events** are contracts with other systems: they require clear schemas, versioning, security, backward compatibility, tenant/correlation fields, and delivery mechanisms. Do not serialize entire aggregates containing internal state into public payloads.

You can structure it as:

~~~text
OrderApplicationService
  |-- order.submit()                     [domain]
  |-- publish/record OrderSubmitted      [domain event]
  |-- map to OrderSubmittedV1            [integration contract]
  |-- INSERT outbox record               [same transaction]
  +-- COMMIT
        |
        +-- relay -> broker -> idempotent consumer
~~~

If an integration event must stay consistent with business data, the application service or an adapter running **in the same transaction** must write the outbox. If an event is only for caching, non-critical metrics, or reconstructible work, an in-process post-commit event may suffice.

## 10. Idempotency, ordering, and system observability

- **Idempotency:** assign a unique eventId per business occurrence. Subscribers executing critical side effects should use eventId/business keys to prevent duplicate processing on retries.
- **Ordering:** within one JVM, listeners can be prioritized with @Order, but with @Async or multi-partition brokers there is no global completion-order guarantee; if per-aggregate ordering is needed, define partition keys, versions, or workflows.
- **Observability:** log eventId, aggregateId, and correlation ID; measure events published, failed callbacks, outbox backlog, and processing latency.
- **Testing:** test commit branches, rollbacks after publication, listener failures, transaction propagation, duplicate events, and crash/retry scenarios.
- **Ownership:** each subscriber needs a clear contract for which facts it handles and what counts as complete; publishers should not treat calling void publishEvent as a guarantee that all side effects succeeded.

## 11. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Publish from controller after service committed and use a transactional listener | No active transaction to register callbacks against | Publish inside the use-case transaction so listeners wait for AFTER_COMMIT |
| Send email inside a regular EventListener when business logic can roll back | Non-DB side effects do not roll back with the DB | Use AFTER_COMMIT or an outbox when durability is required |
| Assume repository.save has already committed | save may not have flushed/committed yet | Distinguish persistence requests from actual commits |
| Pass entire JPA entities/lazy objects | Mutable payloads tied to a session | Pass IDs and necessary snapshots |
| Write to DB in AFTER_COMMIT without starting a new transaction | Old resources may no longer commit | Use REQUIRES_NEW when appropriate or write in the original transaction |
| Treat in-memory Spring events as a durable message queue | Process crashes can lose side effects | Use transactional outbox, retries, idempotency |
| Omit eventId and duplicate checks | Retries can double-charge or send emails twice | Use idempotency keys and processing status tracking |
| Ignore exceptions from synchronous listeners | The use case may roll back unexpectedly | Design clear error boundaries and policies |
| Assume @Async preserves transaction context | New threads do not inherit the transaction | Publish in the right context or adjust the design |

## 12. Checklist before finalizing the design

1. Where is the business fact confirmed? Are event names past-tense and payloads clear?
2. Does the application service own the use case's transaction? Do calls go through the Spring proxy when using @Transactional?
3. Does publishing happen **before the transaction ends**, after valid domain behavior?
4. Which listeners should run **immediately**, and which must wait for **AFTER_COMMIT** or **AFTER_ROLLBACK**?
5. If a rollback happens **after publishing**, could any irreversible side effect have already occurred?
6. Do post-commit callbacks need to write to the database, and is a new transaction opened properly?
7. If the process crashes after commit before notifying/publishing to a broker, how does the system recover?
8. Do event payloads contain PII, lazy entities, or mutable collections?
9. Are eventId, correlation, retries, idempotency, and monitoring in place?
10. Do unit/integration tests verify commits, rollbacks, and required callback ordering?

**Conclusion:** Publishing domain events in the application service clarifies business outcomes at the use-case boundary and reduces coupling. **Publish inside an active transaction** when transactional event listeners are needed, remembering that only AFTER_COMMIT callbacks wait for commit. For integration tasks that must survive crashes, write an **outbox in the same transaction** and design an idempotent relay/consumer.

## Official documentation

- Spring Framework 6.2 — ApplicationContext events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — TransactionalEventListener Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — TransactionSynchronization Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
