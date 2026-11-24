# One Event, One Business Meaning in Domain Event Design

## 1. The core principle

In domain event design, **one event type should express one clear business fact that can be named, verified, and explained independently**. That fact has occurred in the domain; consumers can react to it, but an event is not a request telling a consumer to perform a specific job.

For example, in an e-commerce system:

- `OrderPlaced`: an order has been accepted under domain rules.
- `PaymentCaptured`: the funds have been successfully captured.
- `ShipmentDispatched`: the package has been handed off for shipping.

These three statements have **different truth conditions** and can happen at three different times. An order being placed does **not** necessarily mean funds were captured; funds being captured does **not** necessarily mean goods were shipped.

A good event lets readers complete the sentence: "**What happened in the business?**" without opening a chain of `if (action == ...)` statements or decoding a generic bag of data.

> **One meaning does not mean one listener, one field, one aggregate, one database row, or one event per technical operation.** A single `OrderPlaced` event can be handled by multiple listeners. A single business operation may also produce multiple facts if those facts are genuinely independent.

This principle focuses on **semantics** rather than the number of Java classes. The goal is for event contracts to reflect domain language and invariants accurately, not to proliferate classes for appearance's sake.

## 2. Distinguishing events from commands and CRUD notifications

| Message form | Question it answers | Example | Nature |
| --- | --- | --- | --- |
| **Domain event** | What happened and became true in the domain? | `PaymentCaptured` | Fact in the past |
| **Command** | What should the system try to do? | `CapturePayment` | Intent/request; may be rejected |
| **Query** | What data is needed? | `FindOrderStatus` | Request to read information |
| **CRUD/technical notification** | How did data/infrastructure just change? | `OrderRowUpdated`, `CacheInvalidated` | Infrastructure event, not necessarily a business fact |

Do not name an event `SendWelcomeEmailEvent` if the message is actually used to **command sending an email**. When an event expresses `CustomerRegistered`, multiple independent consumers can decide to send emails, grant promotions, or write audit logs according to their own rules.

Nor should you equate `OrderUpdated` with `OrderCancelled`. Updating data is broad; cancelling an order is a specific business state transition with its own preconditions and consequences.

A domain event may legitimately represent a **failure fact**. For example, `PaymentDeclined` can be a fact if the domain records a declined payment decision. However, `PaymentCaptureRequested` and `PaymentCaptured` differ: one states the request was received, while the other states funds were actually captured.

### State it as an assertion before naming

Try writing the event as a declarative sentence:

- "Order `O-42` was accepted at time T" → `OrderPlaced`.
- "Payment `P-7` for order `O-42` was captured for 125,000 VND" → `PaymentCaptured`.
- "The system must send an invoice" → **command/work item**, not yet the fact that an invoice was issued.
- "The orders table status changed from X to Y" → technical event; ask whether there is a corresponding business milestone.

If you have to add "unless `kind=...`, in which case the meaning is completely different," a single event type is very likely carrying multiple meanings.

## 3. Anti-pattern example: one generic event for every change

A common pattern:

```java
// Illustrates an anti-pattern, not a standalone runnable program.
public record OrderEvent(
        String orderId,
        String action,
        Map<String, Object> payload) {
}

@EventListener
public void onOrderEvent(OrderEvent event) {
    if ("PLACED".equals(event.action())) {
        sendWelcomeMessage(event.orderId());
    } else if ("PAID".equals(event.action())) {
        updatePaymentLedger(event.payload());
    } else if ("CANCELLED".equals(event.action())) {
        releaseInventory(event.orderId());
    }
}
```

The problem is not `record` syntax or `Map` itself. The problem is that the `OrderEvent` type **does not state a specific fact**; the meaning lives in the `action` string and a `payload` structure that shifts per branch.

Consequences:

1. **No type checking**: the `PAID` branch needs `paymentId` and `amount`, yet the compiler cannot enforce that those fields exist.
2. **Consumers must understand every variant**: a consumer that only cares about payment capture still has to depend on a generic type and inspect `action`.
3. **Hard to evolve schemas independently**: changing the payload of the `CANCELLED` branch can affect shared code or tests for `OrderEvent`.
4. **Ambiguous event names and logs**: seeing "OrderEvent received" tells you nothing about what occurred.
5. **Events easily turn into a command router**: a central listener dispatches actions based on `action`, increasing coupling.
6. **Scattered validation**: each branch must verify which fields are required and which states are possible.

A better design when these are three distinct facts:

```java
public record OrderPlaced(
        String orderId,
        Instant occurredAt) {}

public record PaymentCaptured(
        String orderId,
        String paymentId,
        long amountMinor,
        String currency,
        Instant occurredAt) {}

public record OrderCancelled(
        String orderId,
        String reasonCode,
        Instant occurredAt) {}
```

These are **illustrative type declarations**; compiling requires importing `java.time.Instant`, and domain validation rules can be added. Each event has a payload tailored to its own fact; no branching on `action` is needed.

**Not every changing attribute needs its own event.** If a user changes column widths on a personal screen, `UserPreferencesChanged` may suffice or no domain event may be needed at all. There is no need to create `UserTableColumnWidthChanged` unless it carries distinct business value.

## 4. "One meaning" does not mean "one event per detail"

This is the most important balance to strike.

### 4.1. One event can carry multiple data fields

`PaymentCaptured` can carry `paymentId`, `orderId`, amount, currency, timestamp, and event ID. They are **data describing the same fact**: a payment was captured.

There is no need to split this into:

- `PaymentAmountRecorded`,
- `PaymentCurrencyRecorded`,
- `PaymentIdAssigned`,

if those three values are simply attributes of **one intact business outcome**.

### 4.2. One event can have multiple consumers

`OrderPlaced` can be received by audit, analytics, recommendation, and notification. The number of consumers does not dictate the number of event types; splitting into `OrderPlacedForAudit` and `OrderPlacedForAnalytics` just to serve individual consumers distorts the domain language and creates duplication.

### 4.3. One transaction can contain multiple facts

If a workflow establishes two distinct business milestones, it can emit two events. However, **never emit two facts just because the code calls two repositories**: publishing events must be driven by actual business invariants achieved, not by the number of SQL statements.

### 4.4. A composite event can be valid

`CheckoutCompleted` can have its own single meaning if the domain defines "checkout completed" as **one recognized milestone** once all prerequisites are met. Such an event is not automatically wrong just because order placement, payment processing, and inventory reservation happened beneath it.

However, if `CheckoutCompleted` is published at the start of checkout, or if its payload contains `paid/cancelled/shipped` flags with conflicting combinations, that is a sign the meaning is poorly defined.

**The deciding question is not "how many fields?" but "what just became true?"**

## 5. Criteria for splitting events into separate types

A checklist to decide whether two occurrences should be two event types:

| Question | If the answer is "Yes" | Design direction |
| --- | --- | --- |
| Can they occur **independently**? | Order placement succeeds while payment capture has not | Split `OrderPlaced` and `PaymentCaptured` |
| Do they happen at **different times**? | Payment is processed after the order is accepted | Split so event timestamps remain truthful |
| Do they have **different truth conditions/invariants**? | "Valid order" differs from "funds captured" | Split |
| Do they have **different required payloads**? | Payment capture needs `paymentId/amount` | Usually split |
| Do they have **different owners/bounded contexts**? | Ordering confirms the order; Payments confirms capture | Use context-appropriate events; consider translation/integration events |
| Do consumers need **different processing/error policies**? | Order audit vs payment settlement | Supporting signal, not the sole criterion |
| Do they need to be **versioned and evolved independently**? | Payments adds provider-specific metadata | Split if semantics are also independent |
| Does one type have multiple `action/type/status` values that completely change the fact? | PLACED, CANCELLED, REFUNDED | Usually split by fact |
| Is there a clearly recognized **shared milestone** in the domain? | CheckoutCompleted with explicit completion rules | Can keep a dedicated milestone event |

Do not split solely because:

- Two listeners do two different jobs.
- One payload contains many attributes.
- The team wants fewer `if` statements without understanding the domain.
- A field on an entity was just edited.
- An event name exceeds an arbitrary character limit.

### Example of facts and state

`OrderPlaced`, `OrderCancelled`, and `OrderShipped` reflect **business milestone transitions**. An `OrderStatus` enum inside an aggregate can describe the current state, but it **does not automatically replace** knowing "what happened" and "when."

For example, a current status of `SHIPPED` is not enough to infer when payment was captured, or whether the order was ever cancelled and reinstated. The business model must define those facts explicitly rather than arbitrarily inferring events from final state.

## 6. Naming events in the domain language

Names should be clear to domain experts without knowing database table names or Java APIs. A common convention is **domain noun + past-tense verb**, for instance:

| Suggested name | Assertion | Note |
| --- | --- | --- |
| `OrderPlaced` | The order has been accepted | Define specifically what "placed" means in the domain |
| `PaymentAuthorized` | Funds have been authorized/held | **Different** from actually captured |
| `PaymentCaptured` | Funds have been captured | Do not use when only sending a capture request |
| `PaymentDeclined` | The request was declined | Meaningful if the domain records/tracks this outcome |
| `ShipmentDispatched` | Goods were handed over to carrier | Different from "delivered to recipient" |
| `SubscriptionRenewed` | The subscription period was renewed | Clarify whether this includes payment success |

Names to watch out for:

- `OrderChanged`: too broad if it covers unrelated business meanings.
- `DoPayment`: a command/action to perform, not a fact.
- `SaveOrderCompleted`: describes a persistence step, not necessarily domain language.
- `EverythingDone`: lacks a concrete truth condition.
- `OrderPlacedAndEmailSent`: couples two independent facts unless that exact milestone is defined by the domain.
- `EntityUpdatedEvent`: convenient for infrastructure, weak as a business contract.

**There is no universal vocabulary across all organizations.** For instance, "order placed" might mean submitted but unapproved in one domain, while in another it means accepted with inventory reserved. Align on the ubiquitous language with domain experts; identical names do not guarantee identical semantics.

## 7. Payload: carrying enough data to explain the fact

A useful event can contain:

- **Event identity**: `eventId`, aiding diagnostics and deduplication in distributed systems with retries.
- **Business identity**: `orderId`, `paymentId`, or the ID of the relevant aggregate.
- **Occurred time**: `occurredAt` is the business timestamp, distinct from when a consumer receives the event.
- **Core fact data**: captured amount, currency code, cancellation reason, status confirmed under the business contract.
- **Causation/correlation** when tracing is needed: which action or event led to this event, and which workflow ties steps together.
- **Contract version** if the event crosses deployment/storage boundaries and needs controlled schema evolution.

You do not need to copy an entire entity or every database column into an event. A bloated snapshot can accidentally expose PII, couple consumers to internal models, and cause bugs while the entity continues mutating.

Example of a structurally immutable Java record:

```java
public record PaymentCaptured(
        UUID eventId,
        String paymentId,
        String orderId,
        long amountMinor,
        String currency,
        Instant occurredAt) {

    public PaymentCaptured {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(occurredAt, "occurredAt");
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("amountMinor must be positive");
        }
    }
}
```

This is an **illustrative declaration**; it requires importing `java.util.UUID`, `java.util.Objects`, and `java.time.Instant`. `amountMinor` is the count of minor currency units per the application contract (e.g., cents for USD). For VND, clearly define which unit the system uses. Avoid arbitrarily converting decimal currency amounts to `double` to prevent rounding errors.

Records help reduce accidental field mutation after creation, but **they do not make referenced mutable objects inside the record immutable**. If a payload holds a `List`, `Map`, or mutable object, make immutable copies and control the schema. Do not include sensitive data in `toString()` and log the entire event.

### Minimal or full data?

Two common strategies:

1. **Notification-style**: carries only identifiers and timestamps; consumers query needed data. Simple, but couples consumers to query APIs, risks reading state **newer** than when the event fired, and makes offline processing harder.
2. **Event-carried state**: carries enough data for consumers to process the fact without synchronous queries. Increases autonomy, but requires careful schema design, authorization, and versioning.

The choice depends on boundaries and consumer needs. Whichever strategy you pick, the meaning of the event must stay intact.

## 8. Spring Framework 6.2 with Java 17 example: two meanings, multiple listeners

The standalone runnable example below illustrates:

- `OrderPlaced` and `PaymentCaptured` are two event types expressing two distinct facts.
- One `OrderPlaced` event has **two listeners** (audit and notification) while still representing **one meaning**.
- `PaymentCaptured` has its own listener receiving the exact payment data.
- No `action` string, no `Map<String, Object>`, and no forcing consumers to guess an event subtype.

The project uses **Java 17+**, **Spring Framework 6.2.12**, and Maven.

Structure:

```text
domain-event-meaning/
├── pom.xml
└── src/main/java/demo/DomainEventsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>domain-event-meaning</artifactId>
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
                <configuration>
                    <mainClass>demo.DomainEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DomainEventsDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.UUID;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class DomainEventsDemo {

    public record OrderPlaced(
            UUID eventId,
            String orderId,
            Instant occurredAt) {
    }

    public record PaymentCaptured(
            UUID eventId,
            String paymentId,
            String orderId,
            long amountMinor,
            String currency,
            Instant occurredAt) {
    }

    public static class OrderHandlers {

        @EventListener
        @Order(1)
        public void writeAudit(OrderPlaced event) {
            System.out.println("AUDIT order " + event.orderId());
        }

        @EventListener
        @Order(2)
        public void notifyCustomer(OrderPlaced event) {
            System.out.println("NOTIFY order " + event.orderId());
        }
    }

    public static class PaymentHandlers {

        @EventListener
        public void writeLedger(PaymentCaptured event) {
            System.out.println(
                    "LEDGER payment " + event.paymentId()
                    + " amount=" + event.amountMinor()
                    + " " + event.currency());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderHandlers orderHandlers() {
            return new OrderHandlers();
        }

        @Bean
        public PaymentHandlers paymentHandlers() {
            return new PaymentHandlers();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var orderPlaced = new OrderPlaced(
                    UUID.fromString(
                            "00000000-0000-0000-0000-000000000001"),
                    "O-100",
                    Instant.parse("2026-01-01T10:00:00Z"));

            var paymentCaptured = new PaymentCaptured(
                    UUID.fromString(
                            "00000000-0000-0000-0000-000000000002"),
                    "P-200",
                    "O-100",
                    125000L,
                    "VND",
                    Instant.parse("2026-01-01T10:02:00Z"));

            context.publishEvent(orderPlaced);
            context.publishEvent(paymentCaptured);
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines **printed by the program**, excluding environment-dependent logs:

```text
AUDIT order O-100
NOTIFY order O-100
LEDGER payment P-200 amount=125000 VND
```

Explanation:

1. `AnnotationConfigApplicationContext` creates and refreshes the context, registering `@EventListener` methods on `OrderHandlers` and `PaymentHandlers`.
2. `publishEvent(orderPlaced)` sends a plain Java object (a record). Spring Framework supports objects that do not extend `ApplicationEvent`; listeners are selected by event type.
3. Both `writeAudit` and `notifyCustomer` listen to **the same `OrderPlaced`**, without forcing a split into two event types. `@Order` describes listener invocation order in this **synchronous** example.
4. `PaymentHandlers.writeLedger` receives only `PaymentCaptured`, with no need for `action`-string branching. Amount and currency are part of this fact's contract.
5. Events are published sequentially on the default multicaster. If you configure an asynchronous executor, **you cannot rely on listener completion order** like in this example as a system guarantee.

In the example, the two events are constructed directly for easy observation. A real system **must not publish `PaymentCaptured` merely because a callback was invoked**: it must confirm payment capture succeeded according to the domain's authoritative source.

### Not every event needs to extend ApplicationEvent

Since Spring Framework 4.2, `ApplicationEventPublisher.publishEvent(Object)` supports ordinary objects. You can use records as shown above. Only subclass `ApplicationEvent` if you genuinely need API compatibility or a custom design; it is not mandatory to add a superclass just to use `@EventListener`.

### An event type is not where the work is executed

`PaymentCaptured` is **information that funds were captured**, not an object with a `capturePayment()` method. The logic deciding whether funds can be captured belongs in the appropriate application/domain service; consumers listening to the event handle the consequences per their defined responsibilities.

## 9. Where to publish events: after business invariants are satisfied

An important design rule: **do not publish a fact before it is actually true**.

Illustrative application model:

```java
// Illustrative code in an application service, not standalone.
// Assumes orderRepository, eventPublisher, and a suitable transaction boundary exist.
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = Order.place(command);
    orderRepository.save(order);

    eventPublisher.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            Instant.now()));
}
```

Here, `OrderPlaced` is published **after the save call in the application flow**, yet an important boundary remains: if the method is inside an uncommitted transaction, synchronous Spring events can reach listeners **before commit**, and the transaction can still roll back afterward.

Therefore, if the `OrderPlaced` contract means "the order is **durably committed**," publishing directly inside the transaction is not enough. You need to define the fact boundary:

- If the event is an internal domain event tied to changes being evaluated inside the transaction, synchronous listeners may participate in the same transaction depending on invocation and configuration.
- If consumers must react **only after a successful commit**, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for in-process listeners (subject to the limitations in section 10).
- If the event must be delivered **reliably across processes** after commit, consider a **transactional outbox** or a mechanism with verified delivery and send guarantees.

**There is no rule that "merely having `@Transactional` sends events after commit."** Publication timing and listener execution timing are two separate factors.

### Where should the decision logic live?

For example, `CapturePayment` is a command. The payment service must communicate with the payment provider and receive a valid confirmation before announcing `PaymentCaptured`. You must not publish `PaymentCaptured` to ask another consumer to go collect money and treat the fact as already established.

Semantically sound flow:

```text
CapturePayment command
        |
        v
Check rules / call payment provider
        |
        +--> Capture succeeded, state confirmed
        |        |
        |        v
        |    PaymentCaptured event
        |
        +--> Capture failed
                 |
                 v
          Do not publish PaymentCaptured
          (may publish PaymentDeclined if that is a domain fact)
```

An event name must have a **truth condition** that the domain can verify. If the truth condition is unclear, the event will be hard to use correctly even if the Java class looks clean.

## 10. Choosing bounded context and integration boundaries

In Domain-Driven Design, `OrderPlaced` emitted by Ordering may be an **internal domain event** of Ordering. Payments may not need to depend directly on every domain class in Ordering. When facts cross a bounded context or service boundary, consider an appropriate **integration event** contract:

```text
Ordering Domain
     |
     +--> Domain event: OrderPlaced
                 |
                 v
        Outbox / translation / publication
                 |
                 v
        Integration event: OrderAcceptedV1
                 |
                 v
            Other services
```

An integration event's name does not have to differ from the domain event's name, but when semantics and audience differ, a dedicated contract is beneficial. You may need to strip internal fields, normalize identifiers, add a schema version, and define compatibility policies.

Important:

- **One domain event, one meaning** does not mean every bounded context must share the exact same Java class.
- Two contexts may use the same term with different definitions. For example, "order accepted" in Order Management and in Fulfillment might be two different milestones.
- An integration event is a **published contract**, often outliving internal code and requiring versioned evolution.
- Do not publish raw domain entity objects onto a message broker and expect consumers to deserialize every version of your model.
- When forwarding a past fact, external systems must know exactly what it means, including idempotency, ordering scope, and effective timing.

An internal fact can also produce multiple projections or messages for different consumers. That does not change the underlying fact; the difference lies in deployment boundaries and consumption contracts.

## 11. Spring Application Events do not automatically turn facts into durable messages

`ApplicationEventPublisher` is a mechanism for publishing application events within a process/context. By default, `SimpleApplicationEventMulticaster` invokes listeners **synchronously**. When you configure a `TaskExecutor`, some listeners can run asynchronously.

Behaviors to understand:

| Aspect | In-process Spring Application Events |
| --- | --- |
| Delivery | Matching listeners within the application context; may propagate across a context hierarchy |
| Synchronous by default | Yes, when using the default multicaster |
| Async | Possible via a multicaster executor or `@Async` depending on design |
| Persistence | **Does not automatically persist events durably** |
| Crash recovery / retry | **No automatic guarantee** |
| Exactly-once | **Not guaranteed** |
| Execution order | Synchronous call order can be controlled with `@Order`; async completion order is not guaranteed |
| Exceptions | A synchronous listener throwing an exception may propagate back to the publisher, depending on ErrorHandler/config |
| Transactions | Publishing does not mean committed; phases and boundaries must be designed separately |

Consequently, choosing an event type with clean semantics is **necessary but not sufficient** for building a fault-tolerant system. If `PaymentCaptured` must trigger work that cannot be lost, choose durable delivery mechanisms and idempotent consumers rather than merely hoping an `@EventListener` will run.

### TransactionalEventListener is a timing mechanism, not durable storage

```java
// Illustrative usage inside a Spring bean with a transaction manager.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaymentCaptured(PaymentCaptured event) {
    updateReadModel(event);
}
```

The method above assumes `PaymentCaptured` and `updateReadModel(...)` already exist, with imports for `TransactionalEventListener`/`TransactionPhase`. If there is no active transaction, transactional listeners do not run by default unless `fallbackExecution = true` is configured.

An `AFTER_COMMIT` callback does not automatically provide atomic delivery to a broker, does not retry across a process crash, and should not implicitly rely on the old transaction to write new data inside the listener. If you need to write data after commit in a new transaction, define a separate, explicit transaction boundary.

## 12. Event versioning: preserving meaning as schemas evolve

If the underlying fact stays the same while the payload is enriched, you **do not need to create a new business event just because a field was added**. For example, adding `paymentMethodCode` to `PaymentCaptured` does not alter the meaning "funds were captured," even though integration contracts may need versioning for compatibility.

Conversely, if semantics change from "provider accepted the capture request" to "funds were definitely settled," those are **two different facts**; you cannot simply bump the schema version and keep calling both `PaymentCaptured` without updating the contract.

| Change | Typical action |
| --- | --- |
| Adding an optional field without changing meaning | Evolve the schema compatibly if infrastructure allows |
| Changing money representation | Explicit version and migration; do not rely on guesswork |
| Changing the event's truth condition | New name/type/contract or controlled semantic migration |
| A new consumer cares about the same fact | Add a listener; **do not** create a new event type just for a consumer |
| Needs to cross a service boundary | Separate integration contract when beneficial |
| Removing PII | Design schema, migration, and retention policies |

Do not use names like `PaymentCapturedV2` to hide the fact that the V2 event actually asserts a different fact. Document clearly "what V2 changes and what stays the same."

### Immutability of facts once emitted

Once you have announced that `PaymentCaptured` occurred, do not mutate the old event object to turn it into `PaymentRefunded`. If funds were refunded, that is a **new business fact**, typically represented by its own event like `PaymentRefunded` linked to the original transaction.

By the same logic, current business state can change, while the history of past facts cannot be arbitrarily rewritten. Even so, domain events **do not automatically** mean event sourcing; an event-sourced system requires dedicated storage and replay rules.

## 13. Correlation, causation, ordering, and idempotency

Each event should describe exactly one fact, yet related facts can still belong to the same workflow.

Example:

```text
correlationId = checkout-123

OrderPlaced(
    eventId=e1, orderId=O-100, occurredAt=t1)
     |
     | causationId=e1
     v
PaymentCaptured(
    eventId=e2, orderId=O-100, paymentId=P-200, occurredAt=t2)
     |
     | causationId=e2
     v
ShipmentRequested / fulfillment command
```

This diagram shows a relationship pattern, **not** a universal rule that every order is paid before shipment. `correlationId` groups steps of the same logical transaction; `causationId` identifies the message/action that triggered the event if the application tracks it.

### Event ID

`eventId` helps:

- Locate a fact in logs and traces.
- Deduplicate when consumers receive the same message again.
- Record processing attempts and results across integrated systems.
- Distinguish multiple occurrences of the same event type for the same aggregate.

A consumer can store `processedEventId` in the same transaction as its state update to implement idempotency. However, **having an ID alone does not guarantee exactly-once processing**: transactions, retries, and broker delivery semantics still matter.

### Ordering

Events for the same aggregate may have a business order that must be protected. If `OrderCancelled` arrives before `OrderPlaced` at a remote consumer, the consumer needs a policy for late or out-of-order events. Depending on architecture, you can use `aggregateVersion`, sequence numbers, partition keys, or a state machine.

Do not assume that just because two `publishEvent(...)` calls happen sequentially on one thread, every async or remote consumer will process them in that exact order.

## 14. Testing whether an event truly has "one meaning"

Testing is not just checking whether a listener receives the right class; it also verifies **business state before and after**:

| Scenario | Test objective |
| --- | --- |
| Valid order placement | Emits exactly one `OrderPlaced` with appropriate `orderId` and timestamp |
| Rejected order placement | Emits no `OrderPlaced` if business preconditions are not met |
| Order placed but unpaid | Does not prematurely emit `PaymentCaptured` |
| Provider grants authorization without capture | Does not treat authorization as capture |
| Capture succeeds | Emits `PaymentCaptured` with correct `paymentId`, amount, and currency |
| Retry of the same command | Does not unintentionally duplicate the fact; verifies idempotency |
| Multiple listeners for OrderPlaced | Share the same event without duplicating the event per consumer |
| Transaction rollback | Listener behavior and outward dispatch honor the contract |
| Event delivered multiple times via broker | Consumer recognizes the same `eventId` and does not duplicate side effects |
| Schema version change | Old/new consumers are tested for compatibility |

### Suggested test helper

For application service code, you can use a fake `ApplicationEventPublisher` to record published objects. Example helper:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.ApplicationEventPublisher;

public final class RecordingEventPublisher implements ApplicationEventPublisher {
    private final List<Object> published = new ArrayList<>();

    @Override
    public void publishEvent(Object event) {
        published.add(event);
    }

    public List<Object> events() {
        return List.copyOf(published);
    }
}
```

This is a syntactically standalone test helper class (with `spring-context` on the classpath). It does not exercise Spring transactions; it only records calls to `publishEvent(Object)`. To test real listeners, use `AnnotationConfigApplicationContext`/integration tests as in section 8.

Illustrative assertions for a service test:

```java
// Assumes placeOrder succeeded using RecordingEventPublisher.
assertEquals(1, publisher.events().size());
assertInstanceOf(OrderPlaced.class, publisher.events().get(0));
```

This is a **JUnit illustration**, not part of the standalone runnable program in section 8. To test persisted records and transactions, write integration tests against a real database or appropriate test containers.

### Reviewing event contracts with business questions

In code reviews, ask the author to answer:

1. How would a domain expert understand this fact name?
2. Which condition makes the fact true, and where is it verified?
3. If the business operation fails, which events must **not** be published?
4. Can this fact happen multiple times for the same aggregate?
5. What distinguishes multiple occurrences: `eventId`, version, timestamp?
6. Which consumers need it, and is a consumer's existence biasing the event name?
7. Are we merging two independent facts or splitting fields of the same fact?
8. If the process crashes right after commit, what mechanism ensures the event can still be processed?

## 15. Common mistakes and how to fix them

1. **Generic events whose `action`/`type` dictates all semantics**: split when branches genuinely express different facts, using concrete types.
2. **Naming events after consumers**: `OrderPlacedForEmail` breeds duplication; use `OrderPlaced` and let consumers decide whether to send emails.
3. **Naming commands as events**: `CapturePaymentEvent` may merely request capture; use command `CapturePayment` and event `PaymentCaptured` after confirmation.
4. **Publishing events when an operation starts**: calling `OrderShipped` as soon as a shipping label is generated, before goods are handed off.
5. **One class holding conflicting state flags**: `OrderEvent(status, isPaid, isRefunded, isShipped)` yields confusing combinations; identify distinct business milestones instead.
6. **Overly granular events per database column**: produces hundreds of events nobody has a business reason to listen to; focus on facts.
7. **Publishing uncommitted facts while naming them as durable**: define transaction boundaries and publication rules.
8. **Confusing `@TransactionalEventListener` with a delivery guarantee**: after-commit is only an internal execution timing hook, not an outbox.
9. **Exposing PII or whole entities**: restrict payloads to necessary data with schema/privacy policies.
10. **Assuming identical types mean identical semantics across bounded contexts**: align terminology or introduce translation contracts.
11. **Using `@Order` for multi-step business orchestration**: with async or remote execution, completion order is not guaranteed; workflows need proper state machines/sagas.
12. **Changing semantics under the same event name**: older consumers may misinterpret facts; version and document clearly.
13. **Assuming one event type = one event instance**: a single `OrderPlaced` class can be instantiated many times for different orders or business attempts.
14. **Ignoring idempotency and duplicate delivery**: consumers with side effects easily double-write when message brokers retry.
15. **Using internal events instead of mandatory transactional APIs**: if success or failure directly depends on an essential operation's outcome, do not turn it into an optional side effect.
16. **Treating domain events as event sourcing**: publishing events inside an application context does not build a replayable event log.

## 16. Practical design workflow

When modeling a new feature, follow this sequence:

**Step 1 — Write the business story.** Use user/domain expert wording: "Customer places order; order is accepted; payment provider captures funds; order is sent to warehouse."

**Step 2 — Highlight past-tense facts.** For example, `OrderPlaced`, `PaymentCaptured`, `FulfillmentStarted`. Do not turn a command like "send email" into an email-sent fact.

**Step 3 — Specify truth conditions.** `PaymentCaptured` is published only after the provider confirms capture per the domain definition, not while a request is pending.

**Step 4 — Identify boundaries and owners.** Which domain knows for sure the fact is true? Who is responsible for changing state and raising the event?

**Step 5 — Choose minimal data sufficient for consumers.** Define identity, `occurredAt`, essential fields, security, and schema evolution.

**Step 6 — Split or merge based on semantics.** If two concepts can occur and evolve independently, split. If multiple fields jointly substantiate one fact, keep them together.

**Step 7 — Design reliable publishing and consumption.** Match internal Spring events, transactional listeners, outbox, or broker to latency, rollback, and durability requirements.

**Step 8 — Test negative and edge cases.** Do not test only the happy path; test rejected commands, pending payments, rollbacks, duplicates, out-of-order arrivals, and consumer failures.

### Final checklist

- [ ] Does every event type clearly answer "what **happened**?"
- [ ] Are there no `action` strings forcing consumers to branch across unrelated business facts?
- [ ] Are event names in the bounded context's ubiquitous language?
- [ ] Are events published only when their truth conditions are met, with explicit transaction boundaries?
- [ ] Do payloads describe facts without leaking unnecessary entity fields or secrets?
- [ ] Can one event have multiple listeners without creating a separate event type per consumer?
- [ ] Are fields belonging to a single business outcome kept together rather than split per field?
- [ ] Are correlation, identity, idempotency, and schema versioning addressed across boundaries?
- [ ] Are Spring Application Events not mistaken for a persistent message broker?
- [ ] Do tests include cases where an event **must not** be published when the fact has not occurred?

**Conclusion:** "One event, one business meaning" is a contract design principle about **facts that have occurred**, not an instruction to maximize the number of Java records. Separate events by business milestones that have independent truth conditions; keep all data describing the same fact in one clear contract; let multiple consumers listen to the same event when needed. When event semantics are accurate, applications become easier to test, easier to evolve, and less entangled in technical conditionals.

## References

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Martin Fowler — Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)
- [Martin Fowler — What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html)
