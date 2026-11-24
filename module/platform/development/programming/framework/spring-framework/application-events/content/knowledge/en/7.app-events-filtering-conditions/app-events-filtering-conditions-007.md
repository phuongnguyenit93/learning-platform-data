# When Should You Split an Event into Its Own Type in Spring Application Events?

In Spring Framework, an event should express **what happened** or **an explicit business request**. The question "should this be split into a separate event type?" arises when multiple listeners receive the same generic event and then have to check `type`, `action`, `status`, or a series of conditions to decide how to handle it.

For example, an order system publishes `OrderChangedEvent` with `action = CREATED / PAID / CANCELLED`. The invoicing listener only cares about `PAID`; the refund listener only cares about `CANCELLED`. If these states represent **distinct business occurrences**, using `OrderPaid` and `OrderCancelled` is usually clearer and safer. Conversely, if a statistics listener only needs `OrderPlaced` when `totalVnd >= 1_000_000`, filtering on the same event type may already be enough.

This lesson explains the boundary between **filtering an event** and **creating a new event type**, and shows how Spring routes events, how to write listeners, a runnable example, and limitations to keep in mind.

## 1. What Does Spring Use to Route Events?

`ApplicationEventPublisher.publishEvent(Object)` allows publishing any object. The event class is not required to extend `ApplicationEvent`; a Java `record` or POJO works as well. For plain objects, Spring wraps them in `PayloadApplicationEvent` at the dispatch layer, while a listener declaring the matching payload type still receives the original object.

`@EventListener` uses the **parameter type** to select which events the method can handle:

```java
record OrderPlaced(String orderId, long totalVnd) {}
record OrderCancelled(String orderId, String reason) {}

@EventListener
public void onPlaced(OrderPlaced event) {
    // Only handles OrderPlaced.
}

@EventListener
public void onCancelled(OrderCancelled event) {
    // Only handles OrderCancelled.
}
```

This snippet illustrates methods inside a Spring bean; a complete runnable example is in section 4. A listener can further filter objects **whose type already matched** using `@EventListener(condition = "...")`. `condition` uses the Spring Expression Language (SpEL): Spring only invokes the method when the expression evaluates to true.

Distinguish between:

- **Filtering by type:** "Is this an event requesting an order review?" → a dedicated `ReviewRequested` class makes the contract explicit.
- **Filtering by properties:** "Does the newly placed order have a total of at least one million VND?" → same `OrderPlaced`, adding a condition on the data.
- **Filtering by both:** a listener accepts `OrderPlaced` and then selects only high-value orders. This is completely valid when it is still the same business event.

An event **does not exist automatically** just because its class or listener is declared. Business code must actually call `publishEvent(...)` when the event occurs.

## 2. Signs That You Should Split into a Dedicated Event Type

| Sign | Why consider splitting | Example |
| --- | --- | --- |
| Different business behavior/semantics | Readers of the class name immediately know what happened | `PaymentSucceeded` vs `PaymentFailed` |
| Listeners repeatedly `switch`/`if` on `action` | One event is carrying multiple different contracts | `OrderChanged(action)` checked in every listener |
| Required fields differ | One generic type must contain many `null` fields or unrelated data | Successful payment has `transactionId`; failure has `failureCode` |
| Post-event workflow differs in responsibility | A dedicated event signals a new business workflow | `ReviewRequested` starts an approval flow instead of just incrementing a counter |
| Different security/access policies | Reduces risk of broadcasting unnecessary data to all listeners | Fraud-control event carries only needed fields |
| Different lifecycles, versions, and consumers | Each contract can evolve more cleanly | `RefundApproved` separated from `RefundRejected` |
| Multiple teams share a stable meaning | Event name serves as a shared language across modules | `AccountLocked` |
| The triggering condition decides the *kind* of work, not just data selection | The condition is a rule creating a new event, so it belongs in the domain | "A review request has arisen" is a new event |

**Do not split simply because each listener has a minor filter criterion.** For example, one party aggregates orders over one million and another aggregates orders over five million, yet both observe the "order placed" event. Creating `OrderAboveOneMillion` and `OrderAboveFiveMillion` just to serve two reports causes event types to proliferate with every consumer and changing threshold.

## 3. Decision Rules: Filter or New Event?

Answer these four questions in order:

1. **Does the event name describe an independent business fact or request?** If yes, prefer a dedicated type, e.g., `InventoryReservationFailed`.
2. **If one listener is removed, does the event still make sense?** If it is named solely after a single listener's filter, it may not need to be a new type.
3. **Is the publisher responsible for confirming the business condition?** If "requires review" is the outcome of a policy at the source, the source can emit `ReviewRequested` after deciding; do not let every consumer interpret rules differently.
4. **Do the data and invariants differ materially?** When a dedicated type eliminates invalid states such as "failed yet still has a success transaction ID", the benefit far outweighs shortening an `if`.

A practical grouping:

| Situation | Appropriate choice | Reason |
| --- | --- | --- |
| Only process `OrderPlaced` if value ≥ 1 million | `@EventListener(condition=...)` or `if` in listener | Still the order-placed event |
| Order flagged for manual review, starting control workflow | `OrderReviewRequested` | New business meaning |
| Need to distinguish created orders from cancelled orders | `OrderPlaced` and `OrderCancelled` | Two distinct state transitions |
| One notification listener only runs for `region = "VN"` | Filter in listener | Consumer criterion, not a new event |
| Email, SMS, audit all receive `OrderPaid` | One event, multiple listeners | Do not create event types per delivery channel |
| One event with 30 statuses sharing the same fields, yet needing totally different handling | Consider modeling the truly significant state transitions | Avoid turning everything into one catch-all event |

Core rule: **split by differences in business occurrence and data contract; filter by selection criteria within the same event**.

## 4. Complete Example: One Filter Condition, One Dedicated Event

Suppose the system both records orders and may raise review requests. The audit listener needs to see every `OrderPlaced`; the large-order watcher only cares about values from one million VND upward. However, `ReviewRequested` is a work request with its own reason, deserving an independent type.

The following example runs with **Java 17+, Maven, and Spring Framework 6.2.x**; it uses a plain Spring context, requiring no Spring Boot or database.

Create the structure:

```text
spring-event-design/
├── pom.xml
└── src/main/java/demo/EventDesignDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-design</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                    <mainClass>demo.EventDesignDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/EventDesignDemo.java`:

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventDesignDemo {

    public record OrderPlaced(String orderId, long totalVnd) {}

    public record ReviewRequested(String orderId, String reason) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {
        @EventListener
        @Order(1)
        public void audit(OrderPlaced event) {
            System.out.println("AUDIT " + event.orderId());
        }

        @EventListener(condition = "#root.args[0].totalVnd() >= 1000000")
        @Order(2)
        public void watchLargeOrder(OrderPlaced event) {
            System.out.println("LARGE " + event.orderId());
        }

        @EventListener
        public void startReview(ReviewRequested event) {
            System.out.println(
                    "REVIEW " + event.orderId() + ": " + event.reason());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            ApplicationEventPublisher publisher = context;

            publisher.publishEvent(new OrderPlaced("A1", 500_000L));
            publisher.publishEvent(new OrderPlaced("B2", 1_500_000L));

            // Business logic has decided order B2 requires review.
            publisher.publishEvent(
                    new ReviewRequested("B2", "manual risk review"));
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

Output of the `System.out.println` statements (excluding environment-specific Maven/logging messages):

```text
AUDIT A1
AUDIT B2
LARGE B2
REVIEW B2: manual risk review
```

Step-by-step explanation:

1. `OrderPlaced("A1", 500_000)` matches the `audit` method; the `watchLargeOrder` condition is false, so only `AUDIT A1` is printed.
2. `OrderPlaced("B2", 1_500_000)` matches both methods. `@Order(1)` and `@Order(2)` guarantee the order of those two listeners in this synchronous example.
3. `ReviewRequested("B2", ...)` is **an independent publish call**, so the `startReview` listener receives that exact type. `@EventListener` does not automatically infer or generate `ReviewRequested` from a high-value `OrderPlaced`.
4. `#root.args[0]` in the SpEL condition is the listener's `OrderPlaced` parameter. Calling `totalVnd()` matches the Java `record` accessor, independent of parameter names compiled into bytecode.
5. Neither event has to extend `ApplicationEvent`; Spring handles them as payload events.

In a real system, the place calling `publishEvent(new ReviewRequested(...))` must be the component **responsible for the business decision** (such as an application service after applying a risk policy). `main` in this example merely stands in for that component to provide a standalone runnable program.

## 5. Before and After Splitting Types

### Before: One Event Carrying Multiple Meanings

```java
record OrderChanged(String orderId, String action, String reason) {}

// Inside a Spring bean:
@EventListener
public void handle(OrderChanged event) {
    if ("PAID".equals(event.action())) {
        issueReceipt(event.orderId());
    } else if ("CANCELLED".equals(event.action())) {
        releaseInventory(event.orderId());
    }
}
```

This is an **illustrative snippet**; the `issueReceipt` and `releaseInventory` methods belong to application services and are not defined here. Risks of this model include invalid `action` values, `reason` being omitted on cancellation, and every consumer repeating branching logic.

### After: Two Contracts with Clear Meanings

```java
record OrderPaid(String orderId, String paymentId) {}
record OrderCancelled(String orderId, String reason) {}

// Inside a Spring bean:
@EventListener
public void onPaid(OrderPaid event) {
    issueReceipt(event.orderId());
}

@EventListener
public void onCancelled(OrderCancelled event) {
    releaseInventory(event.orderId());
}
```

When `OrderPaid` appears, `paymentId` is part of that type's contract; when `OrderCancelled` appears, `reason` has a clear role. A `record` constructor **does not automatically check for null/blank**, so if stronger invariants are required, add checks in a compact constructor or in the business layer creating the event.

Not every value of a status enum needs its own event class. Split only transitions that have distinct meaning and clear consumers; avoid creating countless `StatusChangedToX` classes if they all truly share one contract.

## 6. Using `condition` in the Right Place

Short example of a listener selecting by property:

```java
@EventListener(condition = "#root.args[0].totalVnd() >= 1000000")
public void trackLargeOrder(OrderPlaced event) {
    // Runs when an OrderPlaced meets the threshold.
}
```

Important rules:

- **Conditions always run after type matching**: SpEL does not turn an `OrderPlaced` into a `ReviewRequested`.
- **Prefer pure, lightweight, predictable conditions**: compare values, states, simple flags; avoid network or database queries inside SpEL.
- **Distinguish business rules from consumer filters**: if a condition decides whether to open a workflow, compute it in the responsible service and emit the appropriate event; if it only decides whether to update a statistics chart, keep it in the listener.
- **Check for null and valid data**: SpEL can fail when invoking an accessor on a null nested object; design payloads and expressions to match the contract.
- **Avoid depending on ambiguous parameter names**: `#root.args[0]` or `#a0` work by index. Use `#orderEvent` by name only when the compiler configuration retains parameter names.
- **Do not use technical tag strings as an implicit contract**: if `event.kind()` has many independent values and consumers all branch on it, reconsider splitting types.

When a condition is long or has many checks, a listener method calling a dedicated service/policy can be easier to read and test. However, if the same policy decides **which event is emitted**, that policy must be applied on the publishing side so listeners do not reach conflicting conclusions.

## 7. Designing Dedicated Events Sustainably

**Name events after what happened or the business intent.** `PaymentCaptured`, `AccountLocked`, and `ReviewRequested` convey meaning better than `PaymentEvent2`, `SpecialEvent`, or `NotifyEmailEvent`. Do not name an event after a consumer if the business domain itself does not have that event.

**Prefer small, immutable payloads.** `record` fits simple data: identifiers, timestamps, required values, reasons, correlation IDs. Do not pass a managed JPA entity just so listeners can read a few fields: entities can mutate, lazy-loading may depend on an active transaction, and unnecessary data is exposed. For mutable data, consider an immutable snapshot.

**Pinpoint the exact time of emission.** `OrderPlaced` must be published at a consistent business point. If an event means "the transaction committed", do not emit it as a post-commit promise while the transaction can still roll back.

**Do not use inheritance as a workaround for conditions.** A class hierarchy `OrderEvent` with dozens of subclasses is only useful when the "is-a" relationship and dispatch semantics truly fit. Avoid listeners accepting a base class and repeatedly using `instanceof`, and beware that a base-class listener will also receive subclass events.

**Account for contract evolution.** Adding new fields, changing semantics, or splitting events affects both publishers and consumers. Within a single internal application, you can refactor simultaneously; across independent module boundaries or durable queues, plan compatibility and versioning separately.

**Do not split per reporting need.** When event counts grow per analytics group, consider keeping one core business event and letting consumers build different projections.

## 8. Spring Events Are Not a Message Broker

Spring Application Events use `SimpleApplicationEventMulticaster` by default and dispatch **synchronously on the publisher's thread**, unless configured otherwise or the listener uses an async mechanism. This has several consequences:

- Synchronous listeners can increase the execution time of `publishEvent(...)`; runtime errors in a listener can propagate to the publisher.
- `@Async` on a listener requires enabling async support and configuring an appropriate executor. When running asynchronously, do not assume the listener finishes before `publishEvent(...)` returns, a fixed processing order, or the same transaction/thread context.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is used when a listener must run according to a transaction phase, yet by default it **does not run if no transaction is active** (unless `fallbackExecution = true` is set). Understand commit timing, exceptions, and data-operation limits in the callback.
- Internal Spring events do not provide durable persistence, guaranteed retries, cross-instance distribution, or exactly-once delivery. When emitting events to external systems after commit is mandatory, consider a transactional outbox and a message broker per system requirements.

Deciding to split an event into its own type and deciding **which transport mechanism delivers the event** are two separate problems. A well-named event type does not automatically guarantee delivery reliability.

## 9. Testing Event-Splitting Decisions and Filter Conditions

For the example in section 4, at minimum cover:

| Case | Published event | Result to verify |
| --- | --- | --- |
| Order below threshold | `OrderPlaced("A1", 500_000)` | Audit runs, large-order filter does not run |
| Order at threshold | `OrderPlaced("C3", 1_000_000)` | Both audit and large-order filter run |
| Order above threshold | `OrderPlaced("B2", 1_500_000)` | Both audit and large-order filter run |
| Review requested | `ReviewRequested("B2", "manual risk review")` | Only the review-request listener is triggered |
| Emit large order only, no review request | `OrderPlaced("B2", 1_500_000)` | No `ReviewRequested` is auto-generated |
| Change classification policy | Same input event, new policy | Test whether policy emits or does not emit the event type independently of listeners |

In integration tests, you can initialize an `AnnotationConfigApplicationContext` with beans recording received events and assert against those lists. If the project includes Spring Boot Test, you can use its event testing utilities, though it is not a prerequisite to understand the mechanism. With async or transaction phases, write tests with a properly configured executor/transaction rather than relying on console print order.

## 10. Common Design Mistakes

1. **Splitting events after listener names**: `SendEmailEvent` and `UpdateDashboardEvent` typically reflect consumer tasks; a business event like `OrderPaid` can serve multiple consumers.
2. **Keeping one "all-purpose" event forever**: numerous `action`/`status` fields and nullable properties make the contract hard to verify, with each listener interpreting it differently.
3. **Publishing multiple event types representing the same fact without a convention**: leads to duplicate handling or consumers updating data twice. Define the relationship between root events and derived events.
4. **Pushing business rules into SpEL on each listener**: the same policy gets duplicated and produces divergent results over time.
5. **Confusing filtering with event creation**: `condition` only decides whether to invoke a listener; to have a new event, you must publish it.
6. **Assuming every listener always runs asynchronously or after commit**: dispatch is synchronous by default; transaction/async mechanisms require explicit configuration.
7. **Renaming or changing the payload of an event with many consumers without checking compatibility**: the new class may be cleaner in design but is still a breaking contract change.
8. **Expecting Spring Application Events to replace durable messaging**: retries, replay, and cross-service delivery require specialized infrastructure.

## 11. Checklist Before Creating a New Event Type

- Can the event be described in one concrete business sentence, independent of listener names?
- Does a new listener only need to filter properties, or is it having to interpret `action` to know **which event** occurred?
- Do the payloads of the two situations have different invariants and required fields?
- Who has authority to decide and publish the event, and when is that decision considered effective?
- Does splitting the type reduce branching, duplication, and invalid states?
- Will the event be processed synchronously, post-transaction, or require durable transport?
- How will existing listeners be affected when adding/splitting/changing the contract?

If the answer is mainly "same event, only different data selection criteria", keep the existing event type and filter at the listener. If the answer is "two distinct business occurrences/obligations with separate contracts", create distinct types and have the business source publish them intentionally.

**References:** [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html), sections *Annotation-based Event Listeners*, *Asynchronous Listeners*, and *Ordering Listeners*.