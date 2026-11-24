# Past-Tense Event Naming in Domain Event Design with Spring Application Events

## 1. What must a domain event tell?

In Domain-Driven Design (DDD), a **domain event** is an assertion that **a notable business fact has occurred**. Therefore, event names typically use the **past tense**:

- `OrderPlaced`: an order has been placed.
- `PaymentAuthorized`: a payment has been authorized.
- `PaymentCaptured`: the funds have been captured.
- `InventoryReserved`: inventory has been reserved.
- `InvoiceIssued`: an invoice has been issued.
- `OrderCancelled`: the order has been cancelled.
- `SubscriptionExpired`: the subscription has expired.

This naming style ensures producers and consumers share the same understanding: the producer does not **order** the consumer around; the producer announces a **fact** that consumers can react to according to their needs. An event should not be named `SendEmail` just because a listener uses it to send an email. The right name describes what **happened in the domain**, such as `OrderPlaced`; sending an email is a consumer-specific reaction.

~~~text
Customer           Application use case       Domain/Repository        Listeners
    |                     |                           |                    |
    | PlaceOrder command  |                           |                    |
    +-------------------->| validate                  |                    |
    |                     +-------------------------->| transition state   |
    |                     |<--------------------------+                    |
    |                     | publish(OrderPlaced)                           |
    |                     +----------------------------------------------->|
    |                     |                       write audit / update UI  |
~~~

**Core rule:** name events in the domain's ubiquitous language in the past tense, and publish them when the fact is genuinely established under domain rules; do not publish a success-result event merely upon receiving a request.

## 2. Distinguishing command, event, and query

| Type | What does the message mean? | Naming pattern | Examples |
| --- | --- | --- | --- |
| **Command** | "Do this"; may be accepted or rejected | Action verb + noun | `PlaceOrder`, `CancelOrder`, `CapturePayment` |
| **Domain event** | "This happened"; records a business fact | Noun + past-tense verb | `OrderPlaced`, `OrderCancelled`, `PaymentCaptured` |
| **Query** | "Read/look up data" | Read verb + noun | `GetOrder`, `FindCustomerOrders` |

For example, `PlaceOrder` is a request to place an order. The use case still has to validate the address, price, quantity, customer status, and so on. `OrderPlaced` should appear only when the system **has accepted placing the order**.

A failed request **does not automatically produce a success event**. However, a failure fact can also be a domain event if the domain needs to record or observe it:

- `OrderRejected`: rejecting the order **occurred** by business decision.
- `PaymentDeclined`: the payment provider **declined** the transaction.
- `InventoryReservationFailed`: reserving inventory **failed** per the domain contract (if modeled as a fact).

Avoid turning every technical `RuntimeException` into `OrderRejected`. A DB timeout is not by default a business decision rejecting an order.

### "Requested" can also be past tense

`RefundRequested` describes the fact "a refund request has been recorded," which differs from the `RequestRefund` command and from `PaymentRefunded` ("the payment has been refunded"). Thus, a principle more important than slapping on an `-ed` suffix is **accuracy about what actually happened**.

## 3. Formulas and linguistic conventions

Common Java convention:

~~~text
<Domain Noun><Past Participle / Past Verb>

Order         + Placed     -> OrderPlaced
Payment       + Captured   -> PaymentCaptured
Invoice       + Issued     -> InvoiceIssued
CustomerEmail + Changed    -> CustomerEmailChanged
Shipment      + Dispatched -> ShipmentDispatched
Subscription  + Expired    -> SubscriptionExpired
~~~

Use **PascalCase** for class/record names and `camelCase` for field names. Choose natural phrasing: not every verb takes `-ed` (e.g., `Sent`, `Paid`, `Sold`). Prefer names that are **concise, identify the subject clearly, and carry business meaning**.

Both naming styles below can be used:

~~~java
public record OrderPlaced(long orderId) { }
public record OrderPlacedEvent(long orderId) { }
~~~

`OrderPlaced` is short and reads like a fact. `OrderPlacedEvent` explicitly indicates the kind in projects that favor an `Event` suffix. Pick **one consistent convention** per module or bounded context; sometimes adding and sometimes dropping the suffix is not a Spring runtime error, but it makes code harder to read and search.

Avoid overly verbose names like `OrderWasSuccessfullyPlacedByCustomerEvent` when `OrderPlaced` suffices. Conversely, `DataChanged` is too vague. Readers need to know **which aggregate or domain concept changed** and **what the specific state transition is**.

## 4. Grammatical past tense is not enough: it must match the business milestone

A domain may have multiple steps:

~~~text
OrderDraftCreated
       |
       v
OrderPlaced
       |
       +--> OrderRejected (depends on model)
       |
       v
OrderConfirmed
       |
       v
PaymentCaptured
       |
       v
OrderShipped
       |
       v
OrderDelivered
~~~

The diagram is only an **example state flow**, not a mandatory workflow for every business. The following events have distinct meanings:

| Event | Contract that must hold |
| --- | --- |
| `OrderCreated` | Order/record was created; may still be a draft |
| `OrderPlaced` | The system has accepted the order-placement action |
| `OrderConfirmed` | The order has been confirmed under business rules |
| `PaymentAuthorized` | Payment gateway authorized the transaction, not necessarily captured yet |
| `PaymentCaptured` | Capture/settlement succeeded |
| `OrderPaid` | The order domain recorded the order reaching the "paid" state |
| `InventoryReserved` | Inventory has been reserved in advance |
| `OrderShipped` | The order has been handed off to shipping per the system's definition |
| `PaymentRefunded` | The refund transaction has actually completed |

Do not treat `PaymentAuthorized` and `PaymentCaptured` as synonymous. Nor replace `OrderPlaced` with `OrderCreated` just because the application called `repository.save(...)`. Names should come from the **ubiquitous language** of domain experts rather than technical APIs.

If a fact can be reversed later, that fact remains part of history. For instance, `PaymentCaptured` can be followed by `PaymentRefunded`, rather than deleting the capture event that already occurred.

## 5. Placing the event at the right point in the use case

A sound flow:

1. Receive a command, e.g., `PlaceOrder`.
2. Validate syntax and business preconditions.
3. Ask the aggregate to perform the valid state transition.
4. Record the outcome according to the persistence/transaction policy.
5. Publish the `OrderPlaced` domain event at the appropriate time.
6. Listeners perform additional behavior such as auditing, projections, and sending notifications.

Counterexample (sketch code; the services/types must exist in a project):

~~~java
// WRONG: the event asserts "placed" before validating and saving the order.
public void placeOrder(PlaceOrder command) {
    publisher.publishEvent(new OrderPlaced(command.orderId()));
    Order order = domainService.validateAndPlace(command);
    orderRepository.save(order);
}
~~~

If validation or the repository fails, listeners could have already received `OrderPlaced` even though the business operation never completed. The name **placed** becomes false.

Better at the processing-flow level:

~~~java
// ILLUSTRATION: establish valid state first, then publish.
public void placeOrder(PlaceOrder command) {
    Order order = domainService.validateAndPlace(command);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Even here, you still need to distinguish **when the event is published** from **when the transaction commits** (section 8). Reordering `save`/`publish` matters for domain state, but does not by itself turn all listener side effects into an atomic transaction.

## 6. Java 17+ example: PlaceOrder command and OrderPlaced event

This example runs with **Spring Framework 6.2.8** and JDK 17+, without Spring Boot. To focus on event naming and lifecycle, it uses an **in-memory store** with no DB connection.

Goal: when the command is valid, the service saves the state and publishes `OrderPlaced`; the listener receives the fact and logs it. When the command is rejected due to a negative total, **no** success event is emitted.

### 6.1. Directory structure

~~~text
domain-event-naming/
├── pom.xml
└── src/main/java/DomainEventNamingDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>domain-event-naming</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>DomainEventNamingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. DomainEventNamingDemo.java

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventNamingDemo {

    // Command: requests an action, may be rejected.
    public record PlaceOrder(long orderId, long totalVnd) { }

    // Domain event: fact "order has been placed".
    public record OrderPlaced(long orderId, long totalVnd) { }

    public static final class InMemoryOrders {
        private final Map<Long, Long> totals = new ConcurrentHashMap<>();

        public boolean insertNew(long orderId, long totalVnd) {
            return totals.putIfAbsent(orderId, totalVnd) == null;
        }

        public int size() {
            return totals.size();
        }
    }

    public static final class OrderService {
        private final InMemoryOrders store;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                InMemoryOrders store,
                ApplicationEventPublisher publisher
        ) {
            this.store = store;
            this.publisher = publisher;
        }

        public void handle(PlaceOrder command) {
            if (command.orderId() <= 0 || command.totalVnd() < 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            if (!store.insertNew(
                    command.orderId(), command.totalVnd())) {
                throw new IllegalStateException("Duplicate order");
            }

            System.out.println(
                "STATE_CHANGED order=" + command.orderId()
            );

            // State has transitioned; now publish the fact.
            publisher.publishEvent(
                new OrderPlaced(command.orderId(), command.totalVnd())
            );
        }
    }

    public static final class AuditListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "EVENT OrderPlaced order=" + event.orderId()
                + " totalVnd=" + event.totalVnd()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InMemoryOrders inMemoryOrders() {
            return new InMemoryOrders();
        }

        @Bean
        OrderService orderService(
                InMemoryOrders store,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(store, publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service = context.getBean(OrderService.class);
            InMemoryOrders store = context.getBean(InMemoryOrders.class);

            service.handle(new PlaceOrder(101, 230_000));

            try {
                service.handle(new PlaceOrder(102, -10));
            } catch (IllegalArgumentException ex) {
                System.out.println("REJECTED negative total");
            }

            System.out.println("TOTAL_ORDERS=" + store.size());
        }
    }
}
~~~

Run from the `domain-event-naming` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed to `stdout` by the program, ignoring auxiliary Maven messages:

~~~text
STATE_CHANGED order=101
EVENT OrderPlaced order=101 totalVnd=230000
REJECTED negative total
TOTAL_ORDERS=1
~~~

### 6.4. Why does this output happen?

- `PlaceOrder(101, 230_000)` is a **command**. The service validates input, saves state, and prints `STATE_CHANGED`.
- After the state is accepted, `publisher.publishEvent(new OrderPlaced(...))` publishes the **fact**. `AuditListener` has an `@EventListener` method with parameter `OrderPlaced`, so Spring invokes it.
- The default `SimpleApplicationEventMulticaster` configuration executes ordinary listeners **synchronously on the publisher thread**, so the listener's log appears before `handle` returns.
- `PlaceOrder(102, -10)` is rejected by validation before insertion; there is no `EVENT OrderPlaced` line for order 102.
- `TOTAL_ORDERS=1` shows that only valid commands increase the order count.

**Intentional limitation of the example:** `ConcurrentHashMap` is not a transactional database. If the listener throws an error after `insertNew`, the map modification does not automatically roll back. The example illustrates **naming, business facts, and publication ordering**, not atomic transactions or durability.

## 7. Spring dispatches events by type, not by checking grammatical tense

Since version 4.2, Spring Framework allows publishing **POJOs/records** via `ApplicationEventPublisher.publishEvent(Object)`. `OrderPlaced` does not have to extend `ApplicationEvent`:

~~~java
public record OrderPlaced(long orderId) { }

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Handle event of exact type OrderPlaced.
}
~~~

This is illustrative code placed inside appropriate classes/beans. In a real application, the bean containing the listener must be managed by Spring; the method can be named `onOrderPlaced` or `handle`, while the `OrderPlaced` parameter determines which event type is received. Adding the `Event` suffix to a class is strictly a **convention**; Spring does not inspect the name to guess whether it is a command or an event.

When multiple listeners listen for `OrderPlaced`, each listener can perform independent work: auditing, updating projections, sending notifications. The producer should not rename the event to `SendConfirmationEmail` for a single listener. **Domain event names must be independent of how consumers react.**

### Events are not orders to other systems

A consumer of `OrderPlaced` may choose not to act because it falls outside its scope, or simply record information. However, when an event is modeled as a fact, the consumer **should not act as the gatekeeper deciding whether placing the order succeeded**. Mandatory checks belong in the use case, domain service, or explicitly orchestrated workflow/command.

## 8. Does "has happened" mean the database has committed?

**Not automatically.** In a use case with `@Transactional`:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = domainService.place(command);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

This is **sketch code** inside a project that already has a domain service/repository and transaction configuration. It is not a standalone compilable file.

`publisher.publishEvent(...)` may run **before the transaction actually commits**. If the commit fails or subsequent code throws an exception causing a rollback, synchronous `@EventListener` handlers may have already processed the event. If a listener immediately sends an email or calls an external API, those effects are not rolled back with the database.

Therefore, distinguish:

- **Domain fact within the execution flow:** the aggregate completed the transition within the use case scope, so the event can be created/published internally.
- **Durably committed fact:** the transaction containing the source state has committed. External consumers usually require this guarantee.
- **Event delivered to the consumer:** this is a separate delivery concern; a database commit does not automatically guarantee external listeners/services received and processed it.

### 8.1. Listeners that run only after commit

Spring supports `@TransactionalEventListener` to bind handlers to a transaction phase:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        // Process only when the transaction has committed successfully.
    }
}
~~~

This illustrative snippet requires importing `Component`, `TransactionalEventListener`, and `TransactionPhase`, along with the `OrderPlaced` type. The default phase of `@TransactionalEventListener` is `AFTER_COMMIT`; when the transaction rolls back, this phase callback is not executed. If published outside a transaction, the listener does not run by default (unless `fallbackExecution=true` is intentionally enabled).

Choose **the right mechanism for the need**—do not rename `OrderPlaced` to `OrderWillBePlaced` just to mask a timing issue.

### 8.2. When durable event delivery is required: transactional outbox

`@TransactionalEventListener(AFTER_COMMIT)` **is not a durable queue**. The process can terminate after commit before listener work finishes; critical notifications could be lost.

For cross-system integrations needing retries, a common option is the **transactional outbox**:

1. In the same transaction, write the order state and an outbox record containing `OrderPlaced` along with an event ID.
2. On rollback, both the order and outbox roll back; on commit, both exist.
3. A dispatcher reads committed outbox records and sends them to a broker or target service.
4. Consumers use the event ID/aggregate ID for idempotent processing; the dispatcher tracks retries and sent status.

An outbox is typically designed for **at-least-once delivery**; it does not automatically yield "exactly once" across all systems. The naming principle stays the same: `OrderPlaced` expresses the business fact, while the outbox/broker is the **transport mechanism**.

## 9. Designing payloads so consumers understand the fact

An event should carry **information about what happened**, without embedding instructions for what consumers must do. Example metadata when used across multiple processes:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    long orderId,
    long aggregateVersion,
    Instant occurredAt,
    long totalVnd
) { }
~~~

In a real system:

- `eventId` identifies the event and supports deduplication on retries.
- `orderId` identifies the aggregate whose state is involved.
- `aggregateVersion` or a sequence number helps control event ordering if consumers need it.
- `occurredAt` is when the business fact was recorded; it is not implicitly the same as sent or received time.
- `totalVnd` must be clearly defined (before/after tax, fees, discounts). An integer VND amount is only a simplified model.

Important design points:

- Prefer immutable payloads like `record`; avoid passing managed JPA entities or mutable objects to async listeners.
- Do not put connections, entity managers, request contexts, or unnecessary secrets into payloads.
- For integration events, consider schema versioning, backward compatibility, and how renaming/field changes affect existing consumers.
- A past-tense name **does not guarantee event uniqueness**. If consumers experience retries, proper idempotency/ordering is still required.

## 10. Misleading names and how to improve them

| Confusing name | Why it is problematic | Better choice |
| --- | --- | --- |
| `CreateOrderEvent` | Looks like a command requesting order creation | `OrderCreated` if a record was actually created; `OrderPlaced` if the order was placed |
| `PayOrderEvent` | Unclear whether it requests payment or confirms payment was collected | `CapturePayment` command; `PaymentCaptured` fact |
| `SendEmailEvent` | Instructs a specific listener | `OrderPlaced` or `CustomerRegistered` if the email is merely a reaction |
| `UserUpdated` | Too generic when there are many kinds of changes | `CustomerEmailChanged`, `AccountSuspended` when matching the domain |
| `OrderSuccessEvent` | Unclear which step succeeded | `OrderPlaced`, `OrderConfirmed`, or `OrderPaid` depending on the milestone |
| `PaymentWasSuccessfullyCapturedEvent` | Long and redundant | `PaymentCaptured`/`PaymentCapturedEvent` |
| `RefundRequest` | Could be an entity, command, or event | `RequestRefund` for command; `RefundRequested` for fact |
| `OrderError` | Technical error or business rejection? | `OrderRejected` only when the domain genuinely rejected it |
| `OrderChange` | Not clearly phrased as a fact | `OrderAddressChanged`, `OrderCancelled`, `OrderConfirmed` |
| `DeliveryDone` | Ambiguous terminology | `OrderDelivered` or `PackageDelivered` depending on the entity |

Not every name with `Updated`, `Created`, or `Changed` is wrong. If the domain genuinely cares about a "profile update occurred" event, `ProfileUpdated` can be valid. However, when the domain distinguishes multiple important transitions, specific names reduce guesswork and coupling.

### Bounded contexts may use different terms

In Sales, `OrderPaid` may represent the state applied to an order. In Payment, `PaymentCaptured` is the fact confirmed by the payment system. A Sales listener may receive `PaymentCaptured`, execute an internal command to record payment, and then publish `OrderPaid` if the Sales aggregate actually changes. **Do not assume two events are the same fact** if the business boundaries do not match.

## 11. Event naming review checklist

Before merging a new `...Event` class, check:

1. **Fact:** is this something that happened, or only something to be done?
2. **Past tense:** does the name use a correct and natural past-tense verb?
3. **Subject:** does the name clearly identify the aggregate/business concept?
4. **Business milestone:** are Created/Placed/Confirmed/Paid/Delivered confused?
5. **Producer:** does the publisher have the authority to assert that fact?
6. **Emission point:** did validation and the transition succeed before the event was created?
7. **Transaction:** do consumers need to see the fact after commit or as a step within the same transaction?
8. **Delivery:** if events cannot be lost, are outbox/retry and idempotency in place?
9. **Payload:** does it have IDs and version/timestamp when needed, while avoiding redundant or sensitive data?
10. **Compatibility:** do name/schema changes affect consumers or external contracts?
11. **Consistency:** are you consistently using `OrderPlaced` or `OrderPlacedEvent`?
12. **Tests:** do success/rejection/rollback/duplicate paths all have clear expectations?

Conventions you can document in architecture guidelines:

~~~text
Command: Verb + Noun        -> PlaceOrder, CancelOrder
Event:   Noun + Past Verb   -> OrderPlaced, OrderCancelled
Query:   Read Verb + Noun   -> GetOrder, FindOrders
Handler: on + EventName     -> onOrderPlaced, onPaymentCaptured
~~~

This is a **design convention**, not a requirement for Spring to publish events. Spring routes events primarily by **Java type/annotations**, not by checking whether English verbs are in the past tense.

## 12. Testing event semantics

For `OrderPlaced`, do not only test that a listener receives the event—verify **when the event is allowed to appear**:

| Scenario | Expectation |
| --- | --- |
| Valid command and order transitions successfully | `OrderPlaced` emitted according to contract |
| Invalid command, rejected before transition | No `OrderPlaced` |
| Duplicate command producing no new state transition | Do not emit another fact if the domain did not actually transition again |
| Capture not completed, only authorized | Only `PaymentAuthorized` if needed; no `PaymentCaptured` |
| Refund only requested | Possibly `RefundRequested`, not `PaymentRefunded` |
| Transaction rolled back | Consumers requiring committed facts must not act falsely; use after-commit/outbox |
| Retry with the same event ID | Consumer creates no duplicate side effects if idempotency is required |
| Two events for the same aggregate arrive out of order | Projection must use version/sequence so it does not overwrite with stale state |

For the demo in section 6, you can replace `System.out.println` with a listener storing events in a `List<OrderPlaced>` in tests, invoke valid and invalid commands, and assert **exactly one event was published**. With real JPA/JDBC transactions, verify **state after commit/rollback**, not merely whether the publisher was called inside an unfinished transaction.

## 13. Common mistakes

1. **Naming events like commands:** `CreateOrderEvent` blurs a request and a fact.
2. **Grammatically past-tense but semantically wrong:** `PaymentCaptured` for a payment that was only authorized.
3. **Publishing events before validation/persistence:** consumers receive "already happened" when the use case has not accepted it.
4. **Believing a past-tense name guarantees transaction commit:** `publishEvent` can run before commit; after-commit/outbox addresses that milestone.
5. **Naming after the listener's action:** `SendWelcomeEmail` is a poor name for a customer-registered event.
6. **Using overly generic names:** `EntityUpdated` forces consumers to guess.
7. **Equating infrastructure errors with domain facts:** a database exception is not `OrderRejected`.
8. **Inconsistent `Event` suffix usage:** mixing naming styles for the same kind of fact.
9. **Confusing an event with current state:** an event is history; the aggregate may have already moved to another state.
10. **Sharing mutable entities in payloads:** delayed listeners may observe altered state, hit lazy loading, or depend on a closed session.
11. **Ignoring duplicates/retries:** event IDs and idempotency are still needed on transports that can redeliver.
12. **Renaming classes and accidentally breaking cross-system contracts:** integration event names/schemas need versioning and migration plans.

## 14. Self-check exercises

1. Classify `PlaceOrder`, `OrderPlaced`, and `GetOrder` as command/event/query.
2. The payment gateway reports authorization succeeded but not yet captured: should you publish `PaymentAuthorized` or `PaymentCaptured`? Why?
3. A refund request was just queued: distinguish `RequestRefund`, `RefundRequested`, and `PaymentRefunded`.
4. Why is `OrderCreated` not always synonymous with `OrderPlaced`?
5. Why does the name `SendEmailAfterOrderPlacedEvent` introduce coupling to a consumer, and what name would you choose instead?
6. If `publisher.publishEvent(new OrderPlaced(...))` runs inside `@Transactional` but the DB rolls back, could a synchronous listener have already processed it? How do you handle it only upon commit?
7. A task must be delivered durably after commit. Is `@TransactionalEventListener(AFTER_COMMIT)` enough to prevent losing the event if the process crashes?
8. Does `OrderPlaced` need to extend `ApplicationEvent`?
9. If a consumer reprocesses a message, which metadata field helps deduplicate it?
10. Write past-tense event names for "inventory reserved," "invoice issued," and "subscription cancelled."

**Suggested answers:** (1) command/event/query; (2) `PaymentAuthorized`; (3) command, fact that the request was recorded, fact that the refund succeeded; (4) Created might only be a draft; (5) `OrderPlaced`/`CustomerRegistered` depending on the domain; (6) yes, use after-commit; (7) no, use a transactional outbox/retry if it must not be lost; (8) no; (9) `eventId`; (10) `InventoryReserved`, `InvoiceIssued`, `SubscriptionCancelled`.

## References

- Spring Framework Reference, *Standard and Custom Events / Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 Javadoc, *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 Javadoc, *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html
