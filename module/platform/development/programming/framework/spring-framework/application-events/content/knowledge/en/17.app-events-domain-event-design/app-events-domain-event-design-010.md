# Keeping Domain Free from Direct Spring Dependencies in Domain Event Design

## 1. Goal: plain Java domain, Spring on the outside

When designing **domain events** in a Spring Framework application, a core principle of Domain-Driven Design (DDD), Clean Architecture, and Hexagonal Architecture is: **business rules and the domain model must not depend directly on Spring's event mechanism, annotations, or container**.

A domain event describes a **business fact that has occurred**: for example, **OrderConfirmed**, **InvoicePaid**, **AccountActivated**. That fact must keep the same meaning if the application replaces Spring with another framework, runs inside a CLI application, or is tested without starting an **ApplicationContext**.

Separate three concerns:

1. **The domain decides what happened:** the aggregate executes valid behavior, updates state, and creates domain events.
2. **The application layer coordinates persistence and event handoff:** calls repository ports, defines transaction boundaries, and requests event dispatch.
3. **Infrastructure adapters connect to Spring:** implement ports using **ApplicationEventPublisher.publishEvent(Object)**, a message broker, or a transactional outbox.

**Rule:** the domain does not import **org.springframework.*** and does not need **@Component**, **@Service**, **@Autowired**, **@Transactional**, **@EventListener**, or **ApplicationEventPublisher**. Those tools are useful in application/infrastructure, not part of the business essence.

This separation is not a cosmetic goal of "fewer annotations"; it enables fast plain-Java domain testing, swapping communication mechanisms without editing business rules, preventing event handlers from accidentally becoming the place enforcing business invariants, and clarifying transaction/durability responsibilities.

## 2. Problems when the domain calls ApplicationEventPublisher directly

A common design:

~~~java
// COUNTEREXAMPLE: domain class coupled directly to Spring.
import org.springframework.context.ApplicationEventPublisher;

public final class Order {
    private final ApplicationEventPublisher publisher;

    public Order(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void confirm() {
        // Validate and update business state...
        publisher.publishEvent(new OrderConfirmed(/* data */));
    }
}
~~~

This snippet **only illustrates a flawed architecture**, not a standalone program. It introduces tight constraints:

- The **Order** aggregate cannot be instantiated or tested simply without a Spring-specific dependency.
- The domain decides *how and when* to publish, even though it does not know whether the repository saved successfully or whether the transaction will commit.
- Switching from Spring in-process events to Kafka, RabbitMQ, or an outbox forces modifying the domain.
- Listeners may be invoked while the aggregate is unsaved or when the transaction later rolls back.
- Calling **publishEvent(...)** gets mixed with maintaining invariants, easily making business logic depend on unclear side effects.

Specifically, **ApplicationEventPublisher** does not guarantee "delivery" and does not create transactions. It is an in-application handoff mechanism; with the default **SimpleApplicationEventMulticaster**, listeners usually run synchronously, yet that is an infrastructure choice, not a domain event contract.

### Another dependency to avoid: domain events extending ApplicationEvent

There is no need to declare:

~~~java
// COUNTEREXAMPLE: forcing the domain event itself to extend a Spring class.
public final class OrderConfirmed extends ApplicationEvent {
    // ...
}
~~~

Spring Framework supports **publishEvent(Object)** and **@EventListener** with **POJO events**. Therefore, you can use a **Java record** or plain Java class as a domain event without extending **ApplicationEvent**. When publishing an object that is not an ApplicationEvent, Spring can wrap it internally in **PayloadApplicationEvent**; POJO-typed listeners still receive the matching payload. The domain does not need to know about this wrapper.

## 3. Correct dependency direction

An easy-to-control structure:

~~~text
                  Spring Framework / Infrastructure
                  +-----------------------------------+
                  | SpringDomainEventAdapter          |
                  | JpaOrderRepository / Outbox       |
                  | @EventListener handlers           |
                  +------------------+----------------+
                                     |
                                     | implements ports
                                     v
                  +-----------------------------------+
                  | Application Layer                 |
                  | ConfirmOrderService               |
                  | OrderRepository (port)            |
                  | DomainEventDispatcher (port)      |
                  +------------------+----------------+
                                     |
                                     | uses
                                     v
                  +-----------------------------------+
                  | Domain Layer                      |
                  | Order aggregate                   |
                  | DomainEvent                       |
                  | OrderConfirmed record             |
                  | Invariants / domain services      |
                  +-----------------------------------+
                             (Plain Java)
~~~

Imports must point **inward from outside** or from application to domain; the domain must not import upward from application/infrastructure/Spring. Infrastructure is allowed to know **ApplicationEventPublisher** and **@EventListener** to turn plain Java events into events dispatched by Spring.

### Responsibility boundaries

| Component | Allowed to know | Should not do |
| --- | --- | --- |
| **Order aggregate** | ID, state, invariants, OrderConfirmed event | Inject publisher, open transactions, call network, or choose a broker |
| **OrderConfirmed** | Needed business data and event name | Extend ApplicationEvent, hold EntityManager or Spring beans |
| **ConfirmOrderService** | Use case, repository port, dispatcher port | Embed Spring multicaster details into the domain |
| **DomainEventDispatcher port** | Event publication contract | Force every domain event to implement a Spring interface |
| **SpringDomainEventAdapter** | **ApplicationEventPublisher**, mapping/dispatch | Contain order-confirmation business rules |
| **Listeners in infrastructure/application** | Execute reactions after events | Replace the aggregate's mandatory invariant checks |
| **Outbox adapter** | Durability, retries, serialization, publication | Couple the domain to brokers or transport schemas |

**OrderRepository** can live in the domain or application layer depending on project conventions; what matters is that the interface belongs to an inner layer while the DB implementation belongs to an outer layer, with no outward imports.

## 4. Designing events in plain Java

A good domain event typically:

- Has a **past-tense** name denoting a fact that occurred: **OrderConfirmed**, not the command **ConfirmOrder**.
- Is **immutable** after creation; a Java **record** is a concise choice for small payloads.
- Contains values subscribers need: **aggregate ID**, business IDs, and timestamp/version if needed.
- Does not contain **ApplicationContext**, managed JPA entities, repositories, services, connections, or framework-lifecycle objects.
- Distinguishes **domain events** from outbound **integration events**. They may reflect the same business meaning, while schema/retention/versioning and public data can differ.

Example:

~~~java
package example.domain;

public interface DomainEvent {
}
~~~

~~~java
package example.domain;

import java.util.Objects;

public record OrderConfirmed(String orderId) implements DomainEvent {
    public OrderConfirmed {
        Objects.requireNonNull(orderId, "orderId");
    }
}
~~~

These two snippets are **two separate files**, requiring no Spring dependencies. **record** generates the constructor, **orderId()** accessor, **equals/hashCode**, and **toString**. For in-process event publishing, do not force the domain to implement **Serializable** merely to use Spring's event publisher.

In systems with a message broker, create a separate **mapping** from domain events to a message envelope containing **eventId**, **aggregateId**, **occurredAt**, **schemaVersion**, and **correlationId** where appropriate. That mapping keeps the domain from being locked into Kafka headers, JSON serialization, or external contract versions.

## 5. Aggregates record events themselves without publishing them

Instead of injecting a publisher, the aggregate stores undispatched events in an internal list. Example:

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {

    private final String id;
    private boolean confirmed;
    private final List<DomainEvent> pendingEvents = new ArrayList<>();

    public Order(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    public String id() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public void confirm() {
        if (confirmed) {
            throw new IllegalStateException("order already confirmed");
        }
        confirmed = true;
        pendingEvents.add(new OrderConfirmed(id));
    }

    public List<DomainEvent> drainEvents() {
        List<DomainEvent> snapshot = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return snapshot;
    }
}
~~~

**Order.confirm()** enforces the invariant "already confirmed cannot be confirmed again," updates state, and **records** OrderConfirmed. It does **not** send the event or depend on listeners succeeding.

This enables unit testing:

1. Create **Order** with a normal constructor.
2. Call **confirm()**.
3. Verify **isConfirmed()** and that **drainEvents()** returns exactly **OrderConfirmed**.
4. Call **confirm()** a second time and verify it is rejected.
5. No Spring Context, database, or message broker required.

**Important note:** clearing the list inside **drainEvents()** as soon as events are pulled is safe only for in-memory demos where failures do not require recovery. In production, if saving or publishing fails after draining, events can be lost. You need dispatch confirmation rules or a transactional **outbox**; the domain still does not need to know about that mechanism.

## 6. Defining ports in the application layer

**DomainEventDispatcher** is an interface used by the application layer. The interface makes no mention of Spring:

~~~java
package example.application;

import example.domain.DomainEvent;

public interface DomainEventDispatcher {
    void publish(DomainEvent event);
}
~~~

The repository is also a port:

~~~java
package example.application;

import example.domain.Order;

public interface OrderRepository {
    Order load(String id);
    void save(Order order);
}
~~~

The use case knows only these ports:

~~~java
package example.application;

import example.domain.DomainEvent;
import example.domain.Order;

public final class ConfirmOrderService {

    private final OrderRepository orders;
    private final DomainEventDispatcher dispatcher;

    public ConfirmOrderService(
            OrderRepository orders,
            DomainEventDispatcher dispatcher) {
        this.orders = orders;
        this.dispatcher = dispatcher;
    }

    public void confirm(String id) {
        Order order = orders.load(id);
        order.confirm();
        orders.save(order);

        for (DomainEvent event : order.drainEvents()) {
            dispatcher.publish(event);
        }
    }
}
~~~

**ConfirmOrderService** has no **@Service**, **@Transactional**, **ApplicationEventPublisher**, or Spring imports. It preserves the application sequence: load the aggregate, execute business logic, save the aggregate, and then request event dispatch.

**The sequence in this demo does not guarantee atomicity.** **save()** and **publish()** can succeed or fail independently; with a real DB, you need a transaction boundary and handling matched to consistency requirements. A later section analyzes this separately.

### Why does the application layer own the interface?

The application layer defines **what it needs**, such as "publish a domain event." Infrastructure decides **how to do it**: Spring event bus, outbox, or broker. If the port interface exposes **ApplicationEvent**, **ApplicationContext**, or Kafka types, dependency inversion has failed.

If a system wants the domain completely independent even of the application layer, placing ports in the application layer is straightforward. The domain only contains its event types and behavior; it does not even know the dispatcher port exists.

## 7. Spring adapter: only infrastructure depends on Spring

Adapter connecting the port to **ApplicationEventPublisher**:

~~~java
package example.infrastructure;

import example.application.DomainEventDispatcher;
import example.domain.DomainEvent;
import org.springframework.context.ApplicationEventPublisher;

public final class SpringDomainEventAdapter
        implements DomainEventDispatcher {

    private final ApplicationEventPublisher publisher;

    public SpringDomainEventAdapter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void publish(DomainEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

The handler can receive **OrderConfirmed** directly:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.context.event.EventListener;

public final class OrderConfirmedListener {

    @EventListener
    public void on(OrderConfirmed event) {
        System.out.println("listener: confirmed " + event.orderId());
    }
}
~~~

**@EventListener** lives in infrastructure, not the domain. Spring discovers the method automatically when the listener is registered as a **Spring bean** and the listener adapter is initialized.

Notably: **DomainEvent** and **OrderConfirmed** are plain Java, yet Spring can still dispatch the object. There is no need for an event wrapper extending **ApplicationEvent** inside the domain.

## 8. Complete runnable Java 17+ example

This Gradle project uses **Spring Framework 6.2.9** only in the composition root and infrastructure. The **domain** and **application** packages import nothing from Spring.

Structure:

~~~text
domain-events-decoupled/
  build.gradle
  src/main/java/example/Main.java
  src/main/java/example/domain/DomainEvent.java
  src/main/java/example/domain/OrderConfirmed.java
  src/main/java/example/domain/Order.java
  src/main/java/example/application/DomainEventDispatcher.java
  src/main/java/example/application/OrderRepository.java
  src/main/java/example/application/ConfirmOrderService.java
  src/main/java/example/infrastructure/InMemoryOrderRepository.java
  src/main/java/example/infrastructure/SpringDomainEventAdapter.java
  src/main/java/example/infrastructure/OrderConfirmedListener.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'example.Main'
}
~~~

Create the exact files below.

**src/main/java/example/domain/DomainEvent.java**:

~~~java
package example.domain;

public interface DomainEvent {
}
~~~

**src/main/java/example/domain/OrderConfirmed.java**:

~~~java
package example.domain;

import java.util.Objects;

public record OrderConfirmed(String orderId) implements DomainEvent {
    public OrderConfirmed {
        Objects.requireNonNull(orderId, "orderId");
    }
}
~~~

**src/main/java/example/domain/Order.java**:

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private boolean confirmed;
    private final List<DomainEvent> pending = new ArrayList<>();

    public Order(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    public String id() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public void confirm() {
        if (confirmed) {
            throw new IllegalStateException("order already confirmed");
        }
        confirmed = true;
        pending.add(new OrderConfirmed(id));
    }

    public List<DomainEvent> drainEvents() {
        List<DomainEvent> result = List.copyOf(pending);
        pending.clear();
        return result;
    }
}
~~~

**src/main/java/example/application/DomainEventDispatcher.java**:

~~~java
package example.application;

import example.domain.DomainEvent;

public interface DomainEventDispatcher {
    void publish(DomainEvent event);
}
~~~

**src/main/java/example/application/OrderRepository.java**:

~~~java
package example.application;

import example.domain.Order;

public interface OrderRepository {
    Order load(String id);
    void save(Order order);
}
~~~

**src/main/java/example/application/ConfirmOrderService.java**:

~~~java
package example.application;

import example.domain.DomainEvent;
import example.domain.Order;

public final class ConfirmOrderService {
    private final OrderRepository orders;
    private final DomainEventDispatcher dispatcher;

    public ConfirmOrderService(
            OrderRepository orders,
            DomainEventDispatcher dispatcher) {
        this.orders = orders;
        this.dispatcher = dispatcher;
    }

    public void confirm(String id) {
        Order order = orders.load(id);
        order.confirm();
        orders.save(order);

        for (DomainEvent event : order.drainEvents()) {
            dispatcher.publish(event);
        }
    }
}
~~~

**src/main/java/example/infrastructure/InMemoryOrderRepository.java**:

~~~java
package example.infrastructure;

import java.util.HashMap;
import java.util.Map;

import example.application.OrderRepository;
import example.domain.Order;

public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> data = new HashMap<>();

    public void seed(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Order load(String id) {
        Order result = data.get(id);
        if (result == null) {
            throw new IllegalArgumentException("order not found: " + id);
        }
        return result;
    }

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }
}
~~~

**src/main/java/example/infrastructure/SpringDomainEventAdapter.java**:

~~~java
package example.infrastructure;

import example.application.DomainEventDispatcher;
import example.domain.DomainEvent;
import org.springframework.context.ApplicationEventPublisher;

public final class SpringDomainEventAdapter
        implements DomainEventDispatcher {

    private final ApplicationEventPublisher publisher;

    public SpringDomainEventAdapter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void publish(DomainEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

**src/main/java/example/infrastructure/OrderConfirmedListener.java**:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.context.event.EventListener;

public final class OrderConfirmedListener {
    @EventListener
    public void on(OrderConfirmed event) {
        System.out.println("listener: confirmed " + event.orderId());
    }
}
~~~

**src/main/java/example/Main.java**:

~~~java
package example;

import example.application.ConfirmOrderService;
import example.application.DomainEventDispatcher;
import example.application.OrderRepository;
import example.domain.Order;
import example.infrastructure.InMemoryOrderRepository;
import example.infrastructure.OrderConfirmedListener;
import example.infrastructure.SpringDomainEventAdapter;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class Main {

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        OrderRepository orderRepository() {
            InMemoryOrderRepository repository = new InMemoryOrderRepository();
            repository.seed(new Order("ORD-7"));
            return repository;
        }

        @Bean
        DomainEventDispatcher domainEvents(ApplicationEventPublisher publisher) {
            return new SpringDomainEventAdapter(publisher);
        }

        @Bean
        ConfirmOrderService confirmOrderService(
                OrderRepository repository,
                DomainEventDispatcher events) {
            return new ConfirmOrderService(repository, events);
        }

        @Bean
        OrderConfirmedListener confirmedListener() {
            return new OrderConfirmedListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(ConfirmOrderService.class);
            System.out.println("caller: begin");
            service.confirm("ORD-7");
            System.out.println("caller: end");
        }
    }
}
~~~

In the **domain-events-decoupled** directory, with **JDK 17+** and **Gradle 8.x** installed:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program itself**:

~~~text
caller: begin
listener: confirmed ORD-7
caller: end
~~~

**Why this order?**

- **caller: begin** is printed before the application service runs.
- The aggregate records **OrderConfirmed** in its pending list; it knows nothing about Spring.
- The service saves the aggregate in **InMemoryOrderRepository**, drains events, and calls **DomainEventDispatcher**.
- **SpringDomainEventAdapter** calls **ApplicationEventPublisher.publishEvent(event)**.
- The context's **SimpleApplicationEventMulticaster**, with default configuration, dispatches listeners synchronously; **OrderConfirmedListener** prints **listener: confirmed ORD-7**.
- When **publishEvent(...)** returns, the service continues and main prints **caller: end**.

**Reliability warning for the demo:** the in-memory repository holds the same objects and has no transactions or durability. If the listener throws an exception, in-memory state has already changed and events have already been drained. The demo only proves **dependency direction and the POJO event mechanism**, not a production-grade delivery pattern.

### Verifying that the domain compiles without Spring

Even though the overall project uses Spring Framework, the three domain files can be compiled separately with **javac**. For example, from the project root directory:

~~~bash
javac -encoding UTF-8 -d domain-classes \
  src/main/java/example/domain/DomainEvent.java \
  src/main/java/example/domain/OrderConfirmed.java \
  src/main/java/example/domain/Order.java
~~~

This uses shell line-continuation syntax **\**; on **PowerShell**, write the same command on **one line**:

~~~powershell
javac -encoding UTF-8 -d domain-classes src/main/java/example/domain/DomainEvent.java src/main/java/example/domain/OrderConfirmed.java src/main/java/example/domain/Order.java
~~~

There is no **spring-context.jar** on the javac classpath; the domain still compiles because it only imports from the JDK. This is a concrete check proving the domain layer has no compile-time Spring dependency.

## 9. Transactions: a Spring-free domain still needs consistency

Decoupling the domain from Spring **does not automatically solve** the save–publish problem. You must define the event's meaning and completion requirements.

### 9.1. Regular @EventListener methods can run before DB commit

If a production application service is wrapped in **@Transactional**, calling **publishEvent(event)** mid-method happens **while the transaction is still active**. With the default synchronous multicaster, **@EventListener** can execute immediately on that call stack. Listeners reading data from another transaction **will not see** the new state yet; if the main transaction rolls back afterward, side effects such as sent emails cannot be automatically recalled.

Risky flow example:

~~~text
BEGIN TX
  -> Order.confirm()
  -> orderRepository.save(order)
  -> publishEvent(OrderConfirmed)
       -> listener sends email IMMEDIATELY
  -> another error, ROLLBACK DB
Result: email was sent, yet order confirmation never committed.
~~~

This is not a bug in the domain record; the bug is **choosing the wrong side-effect timing in infrastructure**.

### 9.2. @TransactionalEventListener(AFTER_COMMIT) belongs in the adapter/handler

If a reaction should run only after the transaction commits successfully, Spring infrastructure can use:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@Component
public final class ConfirmationNotificationHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        // Execute reaction only after the transaction commits successfully.
        // Network calls should have appropriate timeouts, retries, and idempotency.
    }
}
~~~

**This is an illustrative snippet for an application with a transaction manager**, not part of the in-memory program in section 8. It requires a Spring-managed bean and an actually active transaction when the event is published. By default, transactional listeners **do not run** if there is no matching transaction (**fallbackExecution=false**).

**Important:** AFTER_COMMIT cannot roll back an already-completed commit. If the handler needs to write a new DB record, it typically needs a new transaction (**REQUIRES_NEW**) on a Spring-managed service—do not assume the old transaction will commit additional changes. Calls to HTTP/email or brokers still do not become atomic with the database automatically.

### 9.3. When events must not be lost: transactional outbox

If **OrderConfirmed** must be delivered to another system even if the process crashes, an in-memory AFTER_COMMIT callback is still insufficient. Scenario:

~~~text
BEGIN TX
  -> save(order)
  -> write OutboxMessage for OrderConfirmed
COMMIT DB
       |
       +--> worker picks up outbox row
             -> publish to Kafka/RabbitMQ/HTTP
             -> retry on failure
             -> mark as sent
~~~

The **outbox record** is written in the **same DB transaction** as the aggregate changes. The domain still creates only plain Java events; application/infrastructure maps events to outbox messages. The worker handles retries and idempotency.

If the DB committed and the worker crashed, the outbox record remains. If the worker delivered the message and crashed before marking it sent, the event may be sent again; consumers need **idempotent handling** based on event/message IDs. An outbox typically provides the foundation for **at-least-once delivery**, not end-to-end exactly-once by default.

### 9.4. Three dispatch options and trade-offs

| Dispatch style | When appropriate | Limitations |
| --- | --- | --- |
| Synchronous **@EventListener** at publish | Local, fast reactions needing immediate error feedback, with well-understood transactions | Runs before commit if published inside a transaction; blocks the caller |
| **@TransactionalEventListener(AFTER_COMMIT)** | Reactions meaningful only when DB commit succeeds, without absolute crash-recovery guarantees | Callback lives in memory; no automatic retry/durability; skipped by default if published outside a transaction |
| **Transactional outbox + worker/queue** | Work that must be durably stored and completed later | Requires schema, relay/worker, retries, idempotency, monitoring |

Do not follow a rule like "every domain event must be asynchronous." An **event** models a fact; **synchronous/asynchronous/durable** is an outer-layer choice based on the business contract.

## 10. Distinguishing domain events, application events, and integration events

These three terms are related but not synonymous:

**Domain event:** expresses a significant fact within a bounded context; created by the domain; e.g., **OrderConfirmed(orderId)**. It does not need to know whether it travels via Spring or a message broker.

**Spring application event:** an internal object send/receive mechanism within an ApplicationContext via **ApplicationEventPublisher**. A plain Java domain event *can* serve as the payload of this mechanism. Not every Spring event is a domain event: **ContextRefreshedEvent** and **ContextClosedEvent** are framework lifecycle events.

**Integration event:** a communication contract across bounded contexts, services, or external systems. Usually requires schema versions, event IDs, timestamps, correlation, serialization, extensibility, and compatibility rules. Do not export raw domain objects over the wire by default.

Mapping example when publishing to a broker:

~~~text
Domain:
  OrderConfirmed(orderId = "ORD-7")

Infrastructure mapping:
  type          = "order.confirmed.v1"
  eventId       = <unique ID generated by adapter>
  aggregateId   = "ORD-7"
  schemaVersion = 1
  payload       = {"orderId":"ORD-7"}
  occurredAt    = <appropriate domain/application confirmation timestamp>
~~~

This is a **structural description**, not a rigid JSON schema. The adapter can generate **eventId** when writing to the outbox and attach metadata per contract. Avoid publishing entire entities with passwords, sensitive fields, or lazy-loaded associations.

## 11. Testing without Spring: real benefits

With a plain Java domain, invariant logic can be tested without starting a container:

~~~java
// Illustrative snippet in a JUnit 5 test class;
// requires importing @Test, assertions, and the domain types.
@Test
void confirmRecordsOneDomainEvent() {
    Order order = new Order("ORD-7");

    order.confirm();

    assertTrue(order.isConfirmed());
    assertEquals(
            List.of(new OrderConfirmed("ORD-7")),
            order.drainEvents());
    assertTrue(order.drainEvents().isEmpty());
    assertThrows(IllegalStateException.class, order::confirm);
}
~~~

This test verifies: state changed, the event was recorded exactly once, draining cleared the pending list, and confirming a second time is rejected. It **requires no Spring container** and does not test **ApplicationEventPublisher**. Since it is a JUnit 5 snippet, add test dependencies and a test class when integrating into a real project; the standalone program in section 8 still runs without JUnit.

### Fake publisher for testing application services

To test the application layer, use an implementation of the port:

~~~java
final class RecordingDispatcher implements DomainEventDispatcher {
    private final List<DomainEvent> recorded = new ArrayList<>();

    @Override
    public void publish(DomainEvent event) {
        recorded.add(event);
    }

    public List<DomainEvent> events() {
        return List.copyOf(recorded);
    }
}
~~~

This is an **illustrative snippet** to place inside a test class with imports for **DomainEvent**, **DomainEventDispatcher**, **List**, and **ArrayList**. You do not need to mock **ApplicationEventPublisher** in every business unit test; only test the Spring adapter mapping in dedicated integration tests.

### Integration tests for the Spring adapter

Create an **AnnotationConfigApplicationContext**, register the adapter bean and **@EventListener**, invoke the use case, and verify the listener receives **OrderConfirmed**. This is a different test scope from domain unit tests.

If using **@TransactionalEventListener(AFTER_COMMIT)**, tests require a real transaction manager or suitable equivalent, testing commit/rollback and publication context; calling the listener method directly does not prove Spring coordinated the phase.

## 12. Enforcing architecture in build/CI

Separating packages is necessary but not sufficient. The domain can still accidentally import Spring if the team lacks automated checks.

Safeguards:

1. **Separate module:** put **domain** in its own Java/Gradle module declaring zero Spring dependencies. If the domain tries to import **org.springframework.***, compilation fails.
2. **Architecture rules:** use ArchUnit or static checks in CI to verify package **..domain..** does not depend on **org.springframework..**, **..infrastructure..**, or transport tools.
3. **Dependency review:** prevent "sneaky dependencies via shared utilities" pointing outward from domain to infrastructure.
4. **Plain Java tests:** aggregate unit tests must run without creating an **ApplicationContext**.
5. **API review:** event types must not directly contain **ApplicationEvent**, **Message<?>**, **KafkaTemplate**, **EntityManager**, HTTP requests, or container types.

Illustrative ArchUnit rule (**not** a standalone runnable file):

~~~java
noClasses()
    .that().resideInAPackage("..domain..")
    .should().dependOnClassesThat()
    .resideInAnyPackage("org.springframework..", "..infrastructure..");
~~~

To use this in a project, add the ArchUnit dependency and import the corresponding API; the snippet only expresses the rule's intent. Under strict architecture, separating physical modules gives stronger compile-time guarantees than code reviews alone.

**Note on Spring Data @DomainEvents:** Spring Data provides **@DomainEvents** and **@AfterDomainEventPublication** annotations for convenient publication from aggregate repositories. However, placing Spring Data annotations directly inside an aggregate means **the domain depends on the framework**. If your goal is a strictly plain-Java domain, use ordinary pending events with an adapter/application port, or extract events in the repository adapter without importing Spring into the domain. Accepting that coupling can be a deliberate choice in a pragmatic codebase, but it should not be called a completely Spring-independent domain.

## 13. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Domain entity injects **ApplicationEventPublisher** | Domain depends on Spring and dispatch timing | Aggregate records events; application/adapter publishes |
| Domain event **extends ApplicationEvent** | Event is no longer plain Java | Use POJO class/record, publish via **publishEvent(Object)** |
| Putting **@EventListener** directly on a domain class | Domain tied to container, hard to unit test | Place listeners in application/infrastructure |
| Using events to bypass aggregate invariants | State can become invalid if a listener does not run | Enforce invariants in mandatory domain/use-case logic |
| Domain calls Kafka/HTTP inside **confirm()** | Side effects occur before commit, hard to retry | Handle mapping/integration in adapters and use an outbox when needed |
| Publish before DB commit and immediately send email | Email reflects a transaction that may roll back | **AFTER_COMMIT** or outbox |
| Using **@Async** alone to "guarantee eventually" | Tasks can be lost if the JVM crashes | Persistent queue/outbox + retry + idempotency |
| Draining pending events before save succeeds | Events lost if save fails | Transaction/unit of work or outbox with failure handling |
| Publishing the same event in multiple places | Listeners run twice, skewed metrics | Assign a single publication owner, use idempotency/event IDs |
| Putting JPA entities/proxies into events | Lazy loading, transaction leaks, sensitive data | Snapshot needed data and plain Java IDs |
| Reusing domain events forever as public contracts | Domain changes break client schemas | Map to versioned integration events |
| Splitting packages while domain module still depends on Spring | Coupling still exists | Enforce dependencies via modules/CI |
| Domain unit tests always require @SpringBootTest | Slow tests, hard-to-reuse domain | Use plain Java unit tests; separate integration tests for adapters |

## 14. Checklist for framework-independent domain events

Before merging, confirm:

- **Does the event describe a fact that occurred?** Past-tense name, necessary data, not a disguised command.
- **Does the domain import only appropriate Java/internal contracts?** No Spring annotations, ApplicationEventPublisher, or transport types.
- **Does the aggregate enforce its own invariants?** Even if a listener does not run, core rules remain intact.
- **Does the application service use ports?** Dependencies point inward toward the domain, with implementations in infrastructure.
- **Does the Spring adapter receive POJO events?** **@EventListener** sits on beans in outer layers.
- **Do you know whether events are published before or after commit?** Do not assume **publishEvent(...)** means committed.
- **If events must not be lost, are outbox/retry/idempotency in place?** Do not treat in-memory callbacks as durable queues.
- **Are event schemas for external consumers versioned separately?** Do not export raw domain objects without a compatibility contract.
- **Do domain unit tests run without starting Spring?** Are there separate integration tests for adapters/transactions?
- **Does CI block reverse dependencies?** Are module boundaries or ArchUnit rules in place?

**Conclusion:** Good domain event design keeps **business facts in the domain** and **publishing mechanisms on the outside**. Spring Framework can dispatch **POJO events** directly, so there is no need for the domain to extend **ApplicationEvent** or inject **ApplicationEventPublisher**. With this architecture, you can swap adapters from in-process events to an outbox/message broker while preserving your business rules and domain unit test suite.

### Official documentation

- Spring Framework Reference — *Application Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc — *ApplicationEventPublisher.publishEvent(Object)*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Data Commons Reference — *Publishing Events from Aggregate Roots*: https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html
