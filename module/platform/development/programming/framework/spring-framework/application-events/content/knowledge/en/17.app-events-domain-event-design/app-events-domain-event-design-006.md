# Publishing Domain Events from Aggregates in Spring Framework and Spring Data

In Domain-Driven Design (DDD), an **aggregate** is a consistency boundary of the business model: entities and value objects belonging to the same aggregate must maintain business invariants whenever an operation changes state. The **aggregate root** is the object external callers use to request changes. A **domain event** describes a business fact *that has occurred in the model*, such as "an order has been placed," "a payment has been confirmed," or "a credit limit has been changed."

Publishing domain events **from an aggregate** typically has two separate steps:

1. **The aggregate records the event once business rules have been satisfied.** The aggregate knows *what* just changed, without needing to know who will listen, send emails, or update search indexes.
2. **The application/infrastructure layer publishes the recorded events** through `ApplicationEventPublisher`, usually at the repository boundary. Listeners handle appropriate reactions, while transactions govern when commit-dependent processing runs.

Spring Data provides convenient support via `@DomainEvents`, `@AfterDomainEventPublication`, and `AbstractAggregateRoot`. It is essential to understand that **recording**, **publishing**, and **transaction confirmation** are three distinct moments. Spring application events are an in-process mechanism; a successful publish alone does not guarantee messages are durably persisted or delivered to external systems.

## 1. Why should the aggregate decide when an event exists?

Suppose you have a `PurchaseOrder` aggregate with a `place()` operation. If the application service publishes `OrderPlaced` itself before invoking domain rules, a listener could receive a notification about an order that was never valid. If the application service tries to infer events from fields after saving, the logic for recognizing "order placed" can end up duplicated across multiple places.

A more natural expression:

```text
Application Service             Aggregate Root               Repository / Spring
       |                               |                               |
       |---- place(orderNo) ---------->|                               |
       |                               |-- check invariants            |
       |                               |-- update state                |
       |                               |-- registerEvent(OrderPlaced)  |
       |<--- aggregate ----------------|                               |
       |                                                               |
       |---- repository.save(aggregate) ------------------------------>|
       |                                       save aggregate          |
       |                                       read events list        |
       |                                       publish events          |
       |                                       clear events            |
       |<----------------------------- save returns -------------------|
       |                                                               |
       +-- transaction ends: COMMIT or ROLLBACK                        |
```

The aggregate only knows a business event happened when it performs a valid state transition. Infrastructure decides how events are dispatched. This keeps business rules inside the model, lets you test the aggregate without booting Spring, and avoids embedding SMTP/Kafka/HTTP clients inside domain objects.

A few principles when designing events:

- **Past-tense naming:** `OrderPlaced`, `PaymentCaptured`, `SubscriptionCancelled`; an event is something that happened in the model, not a command like `SendEmail`.
- **Clear enough data for handling:** e.g., `orderNumber`, `customerId`, `occurredAt`, or aggregate version if the domain needs it. You do not need to put an entire managed JPA entity into the payload.
- **Immutable when published:** a Java `record` is a readable choice for simple events.
- **Do not leak domain into infrastructure:** aggregates should not call `ApplicationEventPublisher`; calling the publisher directly inside an aggregate couples the model to the container and makes testing harder.
- **One change can raise multiple events:** store the list in registration order; do not assume completion order across asynchronous listeners.

## 2. How does Spring Data automatically publish aggregate events?

Spring Data Commons provides two annotations:

```java
@DomainEvents
Collection<?> domainEvents() {
    return events;
}

@AfterDomainEventPublication
void clearEvents() {
    events.clear();
}
```

This is an **illustrative API snippet**, assuming `events` is the aggregate's list of domain events.

- `@DomainEvents` marks a **no-argument** method returning a single event or a collection of events for the repository to publish.
- `@AfterDomainEventPublication` marks a callback that runs **after Spring Data has published the events**; it is typically used to clear the published list and avoid re-publishing on the next save.
- Spring Data attaches this mechanism to supported repository calls such as `save(aggregate)`, `saveAll(...)`, and certain `delete(...)` variants that accept the aggregate instance itself.
- `deleteById(id)` **is not guaranteed to publish aggregate domain events**, because the repository may not have the aggregate instance available to retrieve events from.
- Direct update/delete queries such as JPQL `@Modifying`, SQL bulk updates, or simply mutating a managed JPA entity and letting dirty checking flush it **are not** repository calls that collect domain events from the aggregate. When taking those paths, you cannot assume Spring Data published the events.

In particular, **`@AfterDomainEventPublication` does not mean `AFTER_COMMIT`**. Events may already have been published and the aggregate's list cleared while the database write transaction has not committed yet. If the transaction later rolls back, there is no automatic mechanism to "put events back into the list."

### 2.1. Concise approach: extending `AbstractAggregateRoot`

Instead of writing both annotations and managing a list manually, Spring Data provides:

```java
import org.springframework.data.domain.AbstractAggregateRoot;

public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    public void place() {
        // Check business rules and transition state first.
        registerEvent(new OrderPlaced("PO-42"));
    }
}
```

This is an **API illustration**, not a standalone persistable entity. `AbstractAggregateRoot` already includes:

| API | Role |
| --- | --- |
| `registerEvent(event)` | Appends an event to the pending list and returns the event |
| `andEvent(event)` | Records an event and returns the aggregate, useful for fluent APIs |
| `domainEvents()` | Returns the event list; annotated with `@DomainEvents` |
| `clearDomainEvents()` | Clears the list after publication; annotated with `@AfterDomainEventPublication` |
| `andEventsFrom(otherAggregate)` | Transfers/collects events from another aggregate when needed |

This list lives in the **aggregate instance's memory**, not as a persisted database column and not as a durable message queue. `AbstractAggregateRoot` marks its internal event storage as transient so it is not persisted as a domain attribute.

Design note: using inheritance introduces a degree of dependency from the domain model onto Spring Data. If a project wants the domain to be completely framework-independent, keep the event list inside the aggregate yourself and let the application/infrastructure layer retrieve, publish, and clear it according to your own contract.

## 3. Complete runnable Java 17+ example: aggregate publishing `OrderPlaced` via Spring Data JPA

The example creates an order using an aggregate root. When the application service calls `repository.save(order)`, Spring Data reads the `OrderPlaced` recorded by `registerEvent(...)` and publishes it to Spring's event multicaster.

Two listeners illustrate the difference:

- `@EventListener` runs **when the event is published** (in this example, while `save(...)` is executing and the application transaction has not ended yet).
- `@TransactionalEventListener(phase = AFTER_COMMIT)` processes **only after the order-creation transaction commits successfully**.

The project uses Spring Boot 3.3, Spring Data JPA, H2, and Java 17+, with no web server.

### 3.1. Structure

```text
aggregate-events-demo/
├── pom.xml
└── src/main/
    ├── java/example/aggregate/
    │   ├── DomainEventsApplication.java
    │   ├── PurchaseOrder.java
    │   ├── OrderPlaced.java
    │   ├── PurchaseOrderRepository.java
    │   ├── PlaceOrderService.java
    │   └── OrderEventListeners.java
    └── resources/application.properties
```

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>aggregate-events-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.aggregate.DomainEventsApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages compatible versions of Spring Data JPA, Hibernate, and H2.

### 3.3. `src/main/java/example/aggregate/OrderPlaced.java`

```java
package example.aggregate;

public record OrderPlaced(String orderNumber) {
}
```

`OrderPlaced` is an immutable event carrying a stable business order number. Listeners do not have to read back the entire JPA entity from the event.

### 3.4. `src/main/java/example/aggregate/PurchaseOrder.java`

```java
package example.aggregate;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    private PurchaseOrder(String orderNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.status = "PLACED";
    }

    public static PurchaseOrder place(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }

        PurchaseOrder order = new PurchaseOrder(orderNumber);
        order.registerEvent(new OrderPlaced(orderNumber));
        return order;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

Key point: `PurchaseOrder.place(...)` enforces the rules for creating a valid order and then **records** `OrderPlaced`. It does not call `ApplicationEventPublisher` directly. The event stays in the instance's memory until Spring Data extracts it at the repository step.

`id` is a technical key generated by the database; `orderNumber` is a business identifier already known before saving, so the event does not depend on obtaining an auto-generated key from the database.

### 3.5. `src/main/java/example/aggregate/PurchaseOrderRepository.java`

```java
package example.aggregate;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

The repository proxy is created by Spring Data. When `save(...)` receives an aggregate holding domain events, the repository mechanism publishes its events according to the `@DomainEvents` contract.

### 3.6. `src/main/java/example/aggregate/PlaceOrderService.java`

```java
package example.aggregate;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository repository;

    public PlaceOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void place(String orderNumber) {
        PurchaseOrder order = PurchaseOrder.place(orderNumber);
        repository.save(order);
        System.out.println("service: repository save returned");
    }
}
```

Placing `@Transactional` on the service **wraps both the save operation and the repository's event publication inside a single transaction**. The transaction has not committed just because `repository.save(...)` returned; when the service method exits normally, Spring's interceptor completes the transaction.

### 3.7. `src/main/java/example/aggregate/OrderEventListeners.java`

```java
package example.aggregate;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderEventListeners {

    @EventListener
    public void whenPublished(OrderPlaced event) {
        System.out.println("listener: published " + event.orderNumber());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void whenCommitted(OrderPlaced event) {
        System.out.println("listener: after commit " + event.orderNumber());
    }
}
```

The `whenPublished` method only acknowledges the publication moment; do not dispatch irreversible external tasks here while the transaction can still roll back. The `whenCommitted` method runs only if the source transaction commits successfully.

### 3.8. `src/main/java/example/aggregate/DomainEventsApplication.java`

```java
package example.aggregate;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DomainEventsApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DomainEventsApplication.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            context.getBean(PlaceOrderService.class).place("PO-42");

            long count = context.getBean(PurchaseOrderRepository.class).count();
            System.out.println("main: saved orders=" + count);
        }
    }
}
```

Invoking `PlaceOrderService` through the Spring bean ensures `@Transactional` is applied by the Spring proxy. Do not instantiate `new PlaceOrderService(...)` directly if you want the transaction interceptor to take effect.

### 3.9. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:aggregate_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.root=ERROR
```

H2 is an in-memory database; `create-drop` creates the schema for this exercise and drops it when the application shuts down. Do not use this setting to manage production database schemas.

### 3.10. Run and observe

From the directory containing `pom.xml`, requiring Java 17+ and Maven:

```bash
mvn -q compile exec:java
```

Lines printed by **the program**, in order (excluding framework or Maven output):

```text
listener: published PO-42
service: repository save returned
listener: after commit PO-42
main: saved orders=1
```

Detailed explanation:

1. `PurchaseOrder.place("PO-42")` creates the aggregate and calls `registerEvent(...)`. **No listener is called** on this line.
2. `repository.save(order)` goes through the Spring Data repository; the repository reads the recorded event list and publishes it via Spring's application event mechanism. Because the default multicaster invokes synchronously, `@EventListener` prints `listener: published PO-42` during the repository operation.
3. After `save(...)` returns, the service prints `service: repository save returned`. The outer transaction **has not ended yet** until the service returns through the interceptor.
4. Spring commits the transaction; `@TransactionalEventListener(AFTER_COMMIT)` prints `listener: after commit PO-42`.
5. `place(...)` returns to `main`; the `count()` query sees **1** saved order.

The takeaway from this example is that **when Spring Data publishes domain events is tied to the repository call**, whereas **when listeners execute depends on listener type and transaction phase**. Never treat an `@AfterDomainEventPublication` callback as proof that the database has committed.

## 4. What if you do not want to extend `AbstractAggregateRoot`?

If the domain model wants to avoid Spring Data's base class, you can declare the event list and annotations directly:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class PureStyleOrder {
    private final List<Object> pendingEvents = new ArrayList<>();

    public void place(String orderNumber) {
        // Check invariants, update state...
        pendingEvents.add(new OrderPlaced(orderNumber));
    }

    @DomainEvents
    protected Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    protected void clearDomainEvents() {
        pendingEvents.clear();
    }
}
```

This is an **API illustration**, not a fully mapped JPA entity, and it still uses Spring Data annotations. The difference from inheritance is direct control over the collection. Do not declare parameters on `@DomainEvents` methods; do not directly return a mutable collection that could be altered unintentionally.

If the requirement is **pure Java domain with no Spring Data dependency even in annotations**, have the aggregate expose only a domain API such as `drainDomainEvents()`, and let an adapter/application service collect, publish via `ApplicationEventPublisher` inside the transaction after saving, and clean up. The adapter must explicitly define when events are drained, cleared, and how errors are handled; in that case Spring Data will **not automatically** publish events just because the aggregate holds a list.

An example separating responsibilities at the application layer (**illustrative code, not standalone**):

```java
@Transactional
public void placeOrder(String orderNumber) {
    PurchaseOrder aggregate = PurchaseOrder.place(orderNumber);
    repository.save(aggregate);

    // If not using Spring Data @DomainEvents, the adapter manually publishes
    // the events returned by the aggregate.
    for (Object event : aggregate.drainDomainEvents()) {
        applicationEventPublisher.publishEvent(event);
    }
}
```

This snippet **does not apply directly** to `PurchaseOrder extends AbstractAggregateRoot` in section 3; it illustrates an alternative design with a custom `drainDomainEvents()` API. Do not combine both manual publishing and `@DomainEvents` for the same event, as that will cause **duplicate publication**.

## 5. Transaction boundary: published events differ from committed data

When Spring Data publishes an event inside a `save(...)` call, the outer transaction's commit may not have happened yet. A newly published event can belong to a transaction that rolls back later.

| Scenario | Synchronous `@EventListener` | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| Order-creation transaction commits successfully | Called immediately upon publish | Called after commit |
| Order-creation transaction rolls back **after** event publication | May have already run and produced side effects | Does not run because there was no successful commit |
| Event published outside a transaction | Runs like a normal listener | Skipped by default because `fallbackExecution = false` |
| Synchronous listener throws an exception before commit | Can cause `save`/service to fail, leading to rollback | Not applicable before commit phase |
| Post-commit listener encounters an error | Not applicable | Cannot roll back the already-committed source transaction |

Therefore:

- Use `@EventListener` when immediate logic **is allowed to participate in the current transaction** or only performs synchronous work that is safe if the transaction rolls back.
- Use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` when processing must run **only after commit**, such as sending notifications or starting another workflow. Post-commit failures do not roll back the original transaction.
- If a post-commit listener needs to write to the database, it usually needs an **explicit new transaction**, such as a `@Transactional(propagation = Propagation.REQUIRES_NEW)` service called through a Spring proxy. Old resources sometimes remain bound after commit, yet will not perform a new commit on the old transaction.
- `@TransactionalEventListener` supports `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` phases; choose based on business semantics, not just callback ordering.

**Very important note:** `AbstractAggregateRoot` clears events after **publication**, not after **commit**. If the transaction rolls back, events already published in memory are not automatically put back into the queue. If the application must reliably emit events matching commit state, you must design a different mechanism.

## 6. Commonly overlooked limitations

### 6.1. Mutating an entity does not mean a Spring Data repository publishes events

Case:

```java
@Transactional
public void changeOrder(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();
    order.changeSomething(); // Assumes method creates a domain event.
    // Does not call repository.save(order).
    // Hibernate may dirty-check to issue UPDATE on flush.
}
```

This is **illustrative code**; `changeSomething()` does not exist in the section 3 class. JPA dirty checking can persist modified fields on flush, yet Spring Data's `@DomainEvents` mechanism is tied to **repository calls**, so recorded events may never be published. If your design relies on `@DomainEvents`, ensure write paths actually invoke repository methods that support publication, even when JPA can auto-flush a managed entity.

### 6.2. `deleteById(...)` and bulk updates/deletes do not guarantee publication

Do not assume "every database change produces a domain event." Spring Data documents `deleteById(...)` as a case you cannot rely on for event extraction because the method can execute deletion without receiving the aggregate instance. JPQL/SQL bulk operations and direct update queries bypass the repository event mechanism even more easily.

When a deletion carries business meaning requiring an event, model the operation on the aggregate and invoke a repository method that accepts the instance, or publish the event explicitly from orchestration.

### 6.3. Saving the same aggregate multiple times does not by default re-emit the same event

After publication, `AbstractAggregateRoot` clears the recorded list via `@AfterDomainEventPublication`. Consequently, if you call `save(order)` again with **no new business change**, do not expect old events to be re-published automatically. Conversely, if the application adds a new event before the next save, the repository can publish the new event.

This is a **per-instance cleanup** mechanism; it does not guarantee exactly-once across multiple requests, replicas, or retries. A business request can be retried and produce another event; consumers still need idempotency where required.

### 6.4. Do not treat domain events as commands

`OrderPlaced` describes what happened; `SendConfirmationEmail` is a request to execute work. A domain event may lead to a command in the application layer, but the aggregate should not know which email service exists.

One event can have multiple relatively independent listeners: updating metrics, writing audits, sending notifications. If B **must succeed after A**, rather than relying solely on listener ordering, build an explicit coordination flow. `@Order` only sets invocation priority under suitable conditions; it does not guarantee completion order for asynchronous tasks.

### 6.5. Do not pass live JPA entities to asynchronous listeners

A managed entity may be tied to the transaction's persistence context and become invalid when callbacks run on another thread or after the context closes. Lazy associations can throw `LazyInitializationException`; mutating entity state inside a listener also makes transaction ownership unclear.

Create immutable events containing essential values/snapshots and IDs so listeners can re-query in their own transaction when needed. Do not send entire object graphs or unnecessary sensitive data.

### 6.6. Spring application events are in-process events only

Spring Data does not automatically create Kafka topics, RabbitMQ messages, durable retries, idempotency keys, or a transactional outbox. If the application stops right **after the database commits but before a listener executes an external task**, the reaction can be lost. If the listener sent the message successfully but the process stopped before recording status, retries can cause duplicates.

For cross-service integration, consider:

1. In the **same transaction** as aggregate data, write an `outbox` record containing `eventId`, `aggregateId`, `eventType`, and payload.
2. An independent dispatcher/worker reads the outbox, sends to a broker or another service, and marks it complete.
3. On failure, the worker retries with backoff; consumers enforce idempotency by event ID.
4. Do not delete an outbox event merely because a publish API was called once; maintain delivery status and recovery handling.

This pattern enables recovery from failures between database commit and message emission. It does not turn every system into absolute end-to-end exactly-once delivery.

## 7. Testing aggregates and the publication mechanism

Separate tests by responsibility:

### 7.1. Aggregate unit tests: no Spring needed

Test that `PurchaseOrder.place(...)`:

- Accepts a valid order number, sets state `PLACED`, and records exactly one `OrderPlaced`.
- Rejects blank numbers, creates no valid aggregate, and emits no business events.
- Does not send emails or call a database merely by registering an event.

Since `registerEvent(...)` is protected and the list is managed by `AbstractAggregateRoot`, if you want to unit-test the event list without reflection, you can expose an appropriate test API on the aggregate or verify via an adapter/contract layer in tests. The goal is to verify **event-creation conditions live inside domain behavior**, not to force tests to know Spring Data internals.

### 7.2. Repository integration tests: with Spring Data JPA

In a test with a real database and Spring context:

1. Create an aggregate and call `repository.save(...)` under a real transaction.
2. Use an event-collecting listener to verify `OrderPlaced` is published by the repository.
3. Verify that saving the aggregate again **without registering a new event** does not duplicate the old event on that instance.
4. With a transaction explicitly rolled back after publishing, verify the `AFTER_COMMIT` listener **does not run**.
5. With a successful commit, verify the `AFTER_COMMIT` listener runs, then query data from an independent transaction/connection to verify the commit.

Do not conclude merely from `repository.save(...)` returning that the transaction committed: `save` may interact with the persistence context before the actual commit. Nor use `Thread.sleep(...)` to assert ordering; use synchronous event collection or latches for async tasks.

### 7.3. Error and idempotency integration tests

Simulate processing the same business request ID twice. Use appropriate unique constraints or idempotency keys in the service to protect state and events at the business level. If using an outbox, test the scenario where the worker publishes successfully and crashes before marking it sent, ensuring duplicate delivery to the consumer does not perform side effects twice.

## 8. Self-assessment questions

**1. Who decides whether `OrderPlaced` actually occurred?**  
The aggregate root, via a business method that checks invariants and records the event.

**2. Does `registerEvent(...)` immediately send the event to listeners?**  
No. It appends the event to the aggregate's list. With Spring Data, publication happens when passing through a supported repository method, such as `save(...)`.

**3. Does `@AfterDomainEventPublication` wait for the database commit?**  
No. The callback is tied to the event being **published**, which differs from the `AFTER_COMMIT` phase of a transaction.

**4. Does modifying a managed entity and relying on JPA dirty checking always publish events?**  
No. Dirty checking and Spring Data repository event publication are two separate mechanisms.

**5. Should `@TransactionalEventListener(AFTER_COMMIT)` be used for sending notifications after saving an order?**  
Yes, if the reaction should only happen after commit. However, it still does not guarantee durable delivery across process crashes. When reliable retries are required, use an outbox.

**6. If `save(order)` is called twice, do domain events always appear twice?**  
No. `AbstractAggregateRoot` clears the event list after publication; a new event requires new business behavior that registers an event. Still, this rule does not replace idempotency when handling repeated requests.

## 9. Official documentation

- [Spring Data JPA Reference — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/repositories/core-domain-events.html)
- [Spring Data Commons Javadoc — AbstractAggregateRoot](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Data Commons Javadoc — DomainEvents](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/DomainEvents.html)
- [Spring Data Commons Javadoc — AfterDomainEventPublication](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AfterDomainEventPublication.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)

