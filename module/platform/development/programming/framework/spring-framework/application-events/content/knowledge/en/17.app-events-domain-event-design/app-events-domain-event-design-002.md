# Events Express What Has Happened

## 1. A domain event is a business fact

A **domain event** is a message describing **an occurrence meaningful to the business that has happened within the domain**. Event names typically use the past tense: `OrderPlaced`, `PaymentCaptured`, `InventoryReserved`, `ShipmentDispatched`.

For example, when the system accepts and creates a valid order, the event might say:

> Order 101 for customer 8 has been placed, with a total value of 250,000 VND, at 10:15 UTC.

That is **a statement about business state**. It does not instruct recipients to send an email, charge money, ship goods, or do anything else. Those actions, if needed, are decisions made by event consumers based on their own rules.

~~~text
Customer submits PLACE ORDER request
             |
             v
     OrderService handles
       ├─ Validate request
       ├─ Apply business rules
       └─ Order accepted
             |
             v
         OrderPlaced
             |
        +----+-----+
        |          |
        v          v
   Audit handler   Notification handler
   records         decides whether to send notification
~~~

**Core point:** an event tells **what happened**. It is not a command controlling a specific object, nor does it guarantee that every subsequent action will succeed.

In **Spring Framework Application Events**, a domain event can be an ordinary Java object passed to `ApplicationEventPublisher`. Spring provides the mechanism to deliver the event to listeners, while **business meaning, publication timing, and data consistency** remain the application's design responsibility.

## 2. Distinguishing commands, events, and state

These three concepts often appear in the same use case but answer different questions:

| Concept | Question answered | Example | Nature |
| --- | --- | --- | --- |
| **Command** | "Try to do what?" | `PlaceOrder`, `CapturePayment`, `ReserveInventory` | Expresses intent/request; may succeed or fail |
| **Domain event** | "What happened?" | `OrderPlaced`, `PaymentCaptured`, `InventoryReserved` | Expresses a fact after a valid state transition |
| **State** | "What is the object like right now?" | `Order.status = PLACED` | Currently persisted state; may continue to change |

Suppose a `PlaceOrder(orderId=101)` command arrives:

1. The service checks the customer, products, and order value.
2. If the data is invalid, the command is rejected. **Do not raise `OrderPlaced`**.
3. If the rules are satisfied, the order transitions to `PLACED`. The domain can create `OrderPlaced` with the data of the occurrence that just happened.
4. Listeners receive the notification and decide how to react.

Some easily confused name pairs:

| Avoid when it is actually a command | Event that expresses the fact more accurately |
| --- | --- |
| `CreateOrderEvent` meaning "please create an order" | `OrderPlaced` after the order has been accepted |
| `SendEmailEvent` meaning "please send an email" | `OrderPlaced`; the notification listener decides whether to send an email |
| `ChargeCreditCardEvent` meaning "please collect payment" | `PaymentCaptured` **only after** funds have actually been captured |
| `OrderNeedsApproval` meaning "please review/approve" | `OrderSubmittedForApproval` once the order has entered the approval workflow |

Past-tense naming is a good convention, but **meaning is the standard**. Renaming `SendEmailEvent` to `EmailSent` when the email has not actually been sent is wrong; it turns a wish into a false statement.

## 3. What should an event contain?

An event needs to describe enough for consumers to **understand what happened** without guessing from the class name. Common fields include:

- **Event identity:** `eventId` can be used for tracing, detecting duplicate processing, or correlating logs in systems with retries.
- **Aggregate/entity identity:** `orderId` identifies the order where the state transition occurred; `customerId` can be included when it is necessary data and aligns with data policies.
- **Business data at the time of occurrence:** `totalCents`, `currency`, quantities, or new status. Select only truly needed data; do not copy the entire entity graph.
- **Timestamp:** `occurredAt` is when the domain recorded the fact. If you need to distinguish DB save time, bus publish time, and consumer receipt time, use separate field names such as `recordedAt` or `publishedAt`; these timestamps are not identical.
- **Contract version** (when events are persisted or integrated across systems): e.g., `schemaVersion` or a version in the envelope so consumers know how to read the payload.
- **Correlation information** (if using distributed workflows): `correlationId`, `causationId` for tracing. Do not put them on every event just because you can.

Example value model:

~~~java
import java.time.Instant;
import java.util.UUID;

// Part of a model, not a standalone program.
public record OrderPlaced(
    UUID eventId,
    long orderId,
    long customerId,
    long totalCents,
    String currency,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

### Keep events stable and hard to mutate

An event expresses **something that happened in the past**, so the payload should be a value snapshot kept stable after creation:

- `record` in Java 17+ fits small, clearly structured events. However, `record` only guarantees immutability of **field references**—it does not automatically make mutable `List`, `Map`, or child objects immutable; create immutable copies when needed.
- Instead of carrying a JPA `OrderEntity` still attached to a persistence context, carry the ID and the required business values. An entity can be mutated, lazy-load outside a transaction, or expose fields that should not be leaked.
- Use clear data types for money. Demo examples use `long totalCents` to avoid floating-point rounding; multi-currency applications need to specify the unit/currency and rounding rules clearly.
- Do not automatically stuff passwords, tokens, card numbers, or unnecessary personal data into events because they may be logged, stored, or delivered to multiple consumers.

**Important:** when the event is named `OrderPlaced`, its payload must reflect **the time the order was placed**, not be replaced with the current status `SHIPPED` on a later read.

## 4. Choosing the right business boundary before publishing an event

A domain event should be created when **a business rule confirms a meaningful state transition**. Do not publish `OrderPlaced` as soon as an HTTP request arrives, because the request may be rejected.

Distinguish three points in time:

~~~text
[1] Command arrives
      |
      | Validate + process
      v
[2] Domain confirms valid change
      |
      | Pending domain event may be created
      v
[3] Data persistence transaction succeeds (if a DB is used)
      |
      v
Consumers outside the transaction may treat the fact as committed
~~~

In systems using DB transactions, **creating the event object at step [2]** does not automatically mean the DB has committed. If the transaction later rolls back, publishing externally too early can make consumers believe an order exists even though the DB discarded the change.

Implementation options depending on your goal:

1. **Work that must share the same transaction:** execute within the current transaction, or use an appropriate pre-commit mechanism when consistency is required. If a consumer failure must roll back the entire use case, post-commit callbacks do not meet this requirement.
2. **Work that should only happen after commit:** use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` in an application with proper transaction management. A post-commit listener is not automatically given a new DB write transaction; if further writes are needed, set up a new transaction explicitly.
3. **Durable event delivery to external systems is required:** write the domain change and an **outbox** record in the same transaction; a separate process delivers the event with retries/idempotency. Do not treat in-memory application events as a durable message queue.

In reactive transactions managed by `ReactiveTransactionManager`, context is stored in the **Reactor Context**, not ThreadLocal. When using transaction-bound event listeners, publish via Spring's `TransactionalEventPublisher` mechanism so the transaction context is carried into the event source. This is a technical detail of the publishing mechanism and does not alter the meaning of `OrderPlaced`.

## 5. Java 17+ example with Spring: publishing "OrderPlaced" when placing an order succeeds

This example intentionally **has no database** to clearly illustrate the difference between **the command requesting an order placement**, **the domain deciding placement succeeded**, and **the listener receiving the fact that occurred**. `OrderService` temporarily stores orders in a `Map`; if a command has a duplicate ID or invalid value, no event is published.

Project:

~~~text
domain-event-fact-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DomainEventDemo.java
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'domain-event-fact-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.DomainEventDemo'
}
~~~

Create `src/main/java/demo/DomainEventDemo.java`:

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventDemo {

    // Command: a request, does not yet say the order was placed successfully.
    public record PlaceOrder(
        long orderId,
        long customerId,
        long totalCents
    ) {}

    // Domain event: snapshot of an accepted occurrence.
    public record OrderPlaced(
        long orderId,
        long customerId,
        long totalCents,
        Instant occurredAt
    ) {}

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;
        private final Clock clock;

        // Single-threaded demo, stored in memory only.
        private final Map<Long, OrderPlaced> orders =
            new LinkedHashMap<>();

        public OrderService(ApplicationEventPublisher publisher,
                            Clock clock) {
            this.publisher = publisher;
            this.clock = clock;
        }

        public void place(PlaceOrder command) {
            if (command.orderId() <= 0 ||
                command.customerId() <= 0 ||
                command.totalCents() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid order data"
                );
            }

            if (orders.containsKey(command.orderId())) {
                throw new IllegalStateException(
                    "Order already exists"
                );
            }

            // With the Map in this demo, this is when the state
            // is accepted; there is no DB transaction.
            OrderPlaced event = new OrderPlaced(
                command.orderId(),
                command.customerId(),
                command.totalCents(),
                Instant.now(clock)
            );

            orders.put(command.orderId(), event);

            // Spring accepts plain payload objects.
            publisher.publishEvent(event);
        }

        public int count() {
            return orders.size();
        }
    }

    public static final class OrderPlacedListener {

        @EventListener
        public void whenOrderPlaced(OrderPlaced event) {
            System.out.println(
                "event: order " + event.orderId()
                + " placed for customer " + event.customerId()
                + ", totalCents=" + event.totalCents()
                + ", occurredAt=" + event.occurredAt()
            );
        }
    }

    @Configuration
    public static class DemoConfig {
        @Bean
        public Clock fixedClock() {
            return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher, Clock clock) {
            return new OrderService(publisher, clock);
        }

        @Bean
        public OrderPlacedListener orderPlacedListener() {
            return new OrderPlacedListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {
            OrderService service = context.getBean(
                OrderService.class
            );

            // Success: creates state and publishes OrderPlaced.
            service.place(new PlaceOrder(101, 8, 25_000));

            // Failure: must not publish another OrderPlaced.
            try {
                service.place(new PlaceOrder(101, 8, 25_000));
            } catch (IllegalStateException ignored) {
                System.out.println("duplicate rejected");
            }

            try {
                service.place(new PlaceOrder(102, 9, -1));
            } catch (IllegalArgumentException ignored) {
                System.out.println("invalid amount rejected");
            }

            System.out.println("orders stored: " + service.count());
        }
    }
}
~~~

Run with JDK 17+ and Gradle in the project directory:

~~~bash
gradle run --quiet
# If Gradle Wrapper is available: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

Lines printed by the program itself, in order (additional logs may appear depending on environment configuration):

~~~text
event: order 101 placed for customer 8, totalCents=25000, occurredAt=2026-01-01T00:00:00Z
duplicate rejected
invalid amount rejected
orders stored: 1
~~~

Explanation:

- `PlaceOrder(101, 8, 25000)` is a command. After validating and recording the state in the `Map`, the service publishes **one `OrderPlaced` event**.
- The `@EventListener` method directly takes a parameter of type `OrderPlaced`, even though the payload does not extend `ApplicationEvent`. Spring supports this payload type through its application event mechanism.
- The duplicate order ID attempt is rejected before recording state or publishing an event. The command with a negative amount also fails. Thus, there is only **one event line**.
- `Clock.fixed` keeps `occurredAt` fixed so output is predictable; real applications usually inject `Clock.systemUTC()` and use a consistent clock.
- In the demo, `Map` is only a temporary storage example that is **not thread-safe, not durable, and has no rollback**. Do not directly apply a "`put` then publish" pattern to a transactional DB system; address the commit boundary from section 4.

**Important limitation of the demo:** `ApplicationEventPublisher` is not a transaction manager. Default synchronous listeners may run directly inside the `publishEvent` call; if a listener throws an exception, it may propagate back to the service while the `Map` has already been modified. The demo only validates and publishes events without implementing rollback or retry mechanisms. If business rules require consistency/durability, proper transactions or an outbox are needed.

## 6. Events say "this happened", not "future outcomes will succeed"

A good event must be precise enough that consumers **do not over-infer**.

Example:

~~~text
OrderPlaced
    ├─ True: the order was accepted/placed according to domain rules.
    ├─ Does NOT mean: the card was charged.
    ├─ Does NOT mean: the items were packed.
    └─ Does NOT mean: the confirmation email was sent.

PaymentCaptured
    └─ True: the system confirmed the payment was captured in the domain sense.

ShipmentDispatched
    └─ True: the package actually entered the dispatched-to-carrier state.
~~~

In an order → payment → shipping flow, use an event for **each genuinely significant occurrence**; do not publish `OrderCompleted` merely because an order placement request was received.

If payment fails, depending on the model you can record a specific fact such as `PaymentDeclined`, rather than publishing `PaymentCaptured` with a `success=false` flag. An event must have clear semantics directly from its name and payload invariants.

For an attempted operation that does not yet have a final outcome, use a command or an appropriate `PENDING` business state. In an asynchronous system, an event can say `PaymentRequested` or `PaymentProcessingStarted` if those **facts actually occurred**; do not disguise them as `PaymentCaptured`.

## 7. Domain events and integration events do not have to be identical

Domain events primarily belong to the **language of a bounded context** and express occurrences in the business model. Integration events are contracts intended for **other systems or bounded contexts**. A domain event can be transformed into an integration event, but exposing raw internal objects externally often creates unnecessary coupling.

| Criterion | Internal domain event | Outbound integration event |
| --- | --- | --- |
| Scope | Within one domain/bounded context | Across system or team ownership boundaries |
| Payload | Fits the domain model, may use Java types | Stable, serializable contract; versioning considered |
| Transport | Can use Spring `ApplicationEventPublisher` | Broker/API/outbox or explicit integration mechanism |
| Durability | Spring application events are in-memory by default | Depends on transport, storage, ACK/retry |
| Deduplication | Depends on business rules | Usually requires `eventId` and idempotent consumers |

For example, an app might publish `OrderPlaced` internally, and an adapter then builds `OrderSubmittedV1` following a public schema for the warehouse service. The mapping must preserve the fact's semantics and not introduce false promises.

Do not confuse **domain events** with **event sourcing**: an application with domain events **does not automatically** store the entire event history to reconstruct state. Event sourcing is a separate architectural choice requiring an event log, ordering, versioning, and replay rules.

## 8. How should consumers react to business facts?

A consumer should receive the right event, use the needed data, and then act according to its own responsibilities. The publisher should not hardcode everything every consumer must do.

Illustrative example, not a standalone program:

~~~java
@Component
class OrderNotificationHandler {

    private final NotificationService notifications;

    OrderNotificationHandler(NotificationService notifications) {
        this.notifications = notifications;
    }

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        notifications.enqueueConfirmation(event.orderId());
    }
}
~~~

This snippet assumes `OrderPlaced`, `NotificationService`, and corresponding imports exist. The `enqueueConfirmation(...)` method is **the consumer's action**, not an "email was sent" claim promised by the event.

Guidelines for designing listeners:

- **Name methods after the consumer's action**, such as `createAuditEntry` or `enqueueOrderConfirmation`, while the event retains a fact-style name like `OrderPlaced`.
- **Do not conflate consumer failure with domain truth.** If sending an email fails, that does not make the fact "the order was placed" false; decide on retries, alerts, or compensation per business requirements.
- **Ensure idempotency under retries or duplicate delivery.** For integration events, you can place a unique constraint on `eventId` on the handling side to avoid writing duplicate audit logs or sending duplicate notifications. Default Spring local events do not automatically guarantee exactly-once across all infrastructure.
- **Do not rely on callback ordering across listeners** unless explicitly configured and tested. A listener should not implicitly depend on another listener having already created data.
- **Consider the side effect's transaction.** Listeners needing to write to the DB after commit must open a proper transaction; listeners calling network APIs or brokers must account for timeouts, transient errors, and crashes.
- **Keep event payloads safe for logging.** If they contain personal data, security policies and retention periods still apply.

## 9. Signs an event is poorly designed

### Mistake 1: The event is a renamed command

~~~java
// Named "Event" but requesting an action:
record SendWelcomeEmailEvent(long customerId) {}
~~~

If the goal is to request sending an email, that is a **command/intent**. If the goal is to react to a successful registration fact, publish `CustomerRegistered` and let the notification handler decide what to send.

### Mistake 2: Raising an event before business logic succeeds

~~~java
publisher.publishEvent(new OrderPlaced(...));
repository.save(order); // Might fail.
~~~

This snippet **only illustrates an anti-pattern**, not independently compilable code. If saving fails or the transaction rolls back, consumers may have already acted on an uncommitted fact. Align publication with the right consistency boundary (transaction-bound callbacks or an outbox).

### Mistake 3: The payload is a live mutable object

~~~java
record OrderPlacedWithEntity(OrderEntity order) {}
~~~

This illustrative snippet assumes an `OrderEntity` class. Even though the wrapper is a `record`, `order` can still be mutated, have lazy associations, or expose persistence structure. Carrying identifiers and intentional value snapshots is safer.

### Mistake 4: Overly generic event names

Names like `DataChanged`, `SystemUpdated`, or `SomethingHappened` force consumers to inspect multiple flags or perform extra queries to understand the business meaning. Prefer `OrderCancelled`, `PriceAdjusted`, or `StockDepleted` when they match the domain language.

### Mistake 5: The event asserts too much

`OrderPlacedAndPaidAndShipped` implies three facts always occur atomically. If they belong to three independent transactions, describe each fact at the right moment. Only use a composite event when the domain **genuinely** has a composite milestone with well-defined semantics.

### Mistake 6: Treating events as a shared database model for consumers to edit

Consumers should not mutate the event object hoping the publisher will see the updated state. An event is a notification, not an entity for multiple parties to update together. Each consumer can maintain its own state within its own system.

## 10. Checklist before naming and publishing a domain event

Answer each question:

1. **What actually happened?** If no valid state transition has occurred yet, it may only be a command or intent.
2. **Does the class name reflect a specific fact?** `OrderPlaced` expresses this more clearly than `OrderEvent`.
3. **When did the fact occur?** Do we need `occurredAt` and to distinguish publish/commit timestamps?
4. **Which object does the consumer need to identify?** Are `orderId`/`aggregateId` and minimal snapshot data included?
5. **Does the event content accidentally expose sensitive data or mutable entities?**
6. **If the transaction rolls back, could consumers still receive the event?** If yes, fix the publication boundary.
7. **If publishing fails or the process crashes, could the system lose the notification?** For durability requirements, consider an outbox/appropriate transport.
8. **If an event arrives twice or late, how does the consumer handle it?** Are `eventId`, versioning, idempotency, or ordering rules in place when truly needed?
9. **Does the event name claim an unproven outcome?** For instance, `PaymentCaptured` only after funds have been captured per the domain contract.
10. **Do tests verify failure cases do not emit false facts?** This is a direct criterion distinguishing events from commands.

A useful test matrix for the order placement example:

| Scenario | State | Expected event |
| --- | --- | --- |
| Valid order placement | New order exists | One `OrderPlaced` with exact ID/amount/timestamp |
| Duplicate order ID | No new order created | No new `OrderPlaced` published |
| Invalid total amount | No order created | No `OrderPlaced` published |
| DB transaction rollback (in DB-backed version) | Not committed | Consumers only receive "committed" facts if publication is designed properly |
| Consumer processing error | Original fact does not automatically reverse | Retry/compensation per designed contract |

## 11. Remember

~~~text
Command:        "Please place order 101"
                    |
                    v
             Business rules
                    |
          Success   |   Failure
            |       |      |
            v       |      v
        OrderPlaced |   No OrderPlaced
            |
            v
    Consumers interested in this fact
    decide on appropriate actions themselves
~~~

**A domain event is an assertion about something that happened in the business.** In Spring, `ApplicationEventPublisher` and `@EventListener` pass and receive that message; they do not replace ensuring domain correctness, commit timing, durability, or contracts with other systems.

## References

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
