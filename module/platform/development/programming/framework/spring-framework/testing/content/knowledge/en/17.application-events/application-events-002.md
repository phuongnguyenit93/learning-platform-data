# Recording Event Types, Payloads, and Occurrence Counts

In a Spring application, a component can publish an event to notify that something has happened. The component publishing the event does not need to directly call each component interested in that occurrence. For example, `OrderService` publishes `OrderPlacedEvent` after creating an order; listeners for auditing, sending notifications, or updating another piece of data can subscribe to this event.

When testing such a flow, we typically need to answer three questions:

- **Event type:** did the application publish the right kind of event?
- **Payload:** does the event carry the right business data?
- **Occurrence count:** did an operation publish the event the expected number of times?

Spring TestContext provides `@RecordApplicationEvents` and `ApplicationEvents` to record application events published during a test run. This allows tests to inspect actual events without having to write a custom listener just to collect data.

## 1. Distinguishing Event Type and Payload

An application event is a message sent via `ApplicationEventPublisher`. The event type indicates **what happened**; the payload contains **the specific details of that occurrence**.

For example, `OrderPlacedEvent` is the event type. `orderId` and `total` are the data accompanying the event. When testing, merely confirming that an `OrderPlacedEvent` exists is not enough: the event might carry the wrong order ID or total amount. Conversely, checking only a payload value without filtering by event type may cause the test to accidentally read a different event with a similar structure.

Spring supports two common representations:

1. An event class extending `ApplicationEvent`. In this case, the concrete class itself is the event type and can be queried directly.
2. A plain object, such as a Java `record`, passed to `publishEvent(Object)`. Spring wraps that object in `PayloadApplicationEvent`; the original data is retrieved via `getPayload()`.

It is good practice to use a consistent representation within a business flow so tests remain easy to read and require fewer special cases.

## 2. Publishing an Event from the Application

The example below uses an event class extending `ApplicationEvent`. The `orderId` and `total` fields form the payload that listeners and tests need to verify.

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;

public final class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;
    private final BigDecimal total;

    public OrderPlacedEvent(Object source, String orderId, BigDecimal total) {
        super(source);
        this.orderId = orderId;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Service publishing the event through `ApplicationEventPublisher`:

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(String orderId, BigDecimal total) {
        // Perform order creation business logic here.
        eventPublisher.publishEvent(
            new OrderPlacedEvent(this, orderId, total)
        );
    }
}
```

A listener can receive the exact event type using `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Record event.getOrderId() and event.getTotal().
    }
}
```

## 3. Enabling the Event Recorder in Spring Test

Place `@RecordApplicationEvents` on a test class that uses Spring TestContext. Spring will provide an `ApplicationEvents` instance to query events published within the scope of each test execution.

```java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@RecordApplicationEvents
class OrderServiceEventTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void publishesOrderPlacedWithExpectedPayloadOnce() {
        orderService.placeOrder("ORD-208", new BigDecimal("250000.00"));

        List<OrderPlacedEvent> publishedEvents = applicationEvents
            .stream(OrderPlacedEvent.class)
            .toList();

        assertThat(publishedEvents).hasSize(1);

        OrderPlacedEvent event = publishedEvents.get(0);
        assertThat(event.getOrderId()).isEqualTo("ORD-208");
        assertThat(event.getTotal()).isEqualByComparingTo("250000.00");
    }
}
```

In this example:

- `@SpringBootTest` initializes the application context so the test calls the real service.
- `@RecordApplicationEvents` enables event recording for the test.
- `applicationEvents.stream(OrderPlacedEvent.class)` retrieves only events of type `OrderPlacedEvent`.
- `hasSize(1)` checks the publication count; subsequent assertions verify the payload.

If you only care about the publication count, you can count directly:

```java
long count = applicationEvents.stream(OrderPlacedEvent.class).count();
assertThat(count).isEqualTo(1L);
```

When a valid operation must publish multiple events of the same type, verify both the expected count and the data of each event. For example, after processing a batch of three orders, the test can confirm there are three `OrderPlacedEvent` instances and the set of `orderId` values matches the three input orders. Checking both count and data helps catch missing events, duplicate publications, or events emitted for the wrong entity.

## 4. Recording Java Object or Record Payloads

Extending `ApplicationEvent` is not required. Spring allows publishing an arbitrary object:

```java
import java.math.BigDecimal;

public record OrderPlaced(String orderId, BigDecimal total) {
}
```

```java
eventPublisher.publishEvent(
    new OrderPlaced("ORD-208", new BigDecimal("250000.00"))
);
```

For objects that do not extend `ApplicationEvent`, Spring creates a `PayloadApplicationEvent` to hold the payload. Therefore, when using `ApplicationEvents`, filter the wrapper and extract the payload inside:

```java
import org.springframework.context.PayloadApplicationEvent;

List<OrderPlaced> payloads = applicationEvents
    .stream(PayloadApplicationEvent.class)
    .map(PayloadApplicationEvent::getPayload)
    .filter(OrderPlaced.class::isInstance)
    .map(OrderPlaced.class::cast)
    .toList();

assertThat(payloads).hasSize(1);
assertThat(payloads.get(0).orderId()).isEqualTo("ORD-208");
assertThat(payloads.get(0).total())
    .isEqualByComparingTo("250000.00");
```

The key point to remember is that the wrapper type is recorded at the application event layer, while `OrderPlaced` is the business payload type. If a test queries `PayloadApplicationEvent.class`, check the payload type as well to avoid counting unrelated payloads by mistake.

## 5. Counting by Event Type and Checking Multiple Publications

`ApplicationEvents` can return all events in the test run or only events of a given type. When verifying occurrence counts, filter by the specific event type:

```java
long orderPlacedCount = applicationEvents
    .stream(OrderPlacedEvent.class)
    .count();

long orderCancelledCount = applicationEvents
    .stream(OrderCancelledEvent.class)
    .count();

assertThat(orderPlacedCount).isEqualTo(1L);
assertThat(orderCancelledCount).isZero();
```

Verifying that an event type did not occur is also useful. For example, when an order is created successfully, the system must publish `OrderPlacedEvent` and must not publish `OrderCancelledEvent`.

If you need to inspect events in publication order, you can call the no-argument `stream()`:

```java
var allEvents = applicationEvents.stream().toList();
```

Only assert on ordering when ordering is part of the business contract. With asynchronous listeners, processing order may differ from publication order.

## 6. Event Published vs. Listener Processed

This is an important boundary when designing assertions:

- `ApplicationEvents` records application events published into the context.
- It is not a counter of how many times each listener was invoked.
- One event can be received by multiple listeners; the number of published events is still one.
- A listener can fail during processing even though the event was published successfully.

Therefore, separate the two testing goals:

**Testing the event publication contract:** use `@RecordApplicationEvents` to confirm event type, payload, and publication count as shown in the examples above.

**Testing listener behavior:** verify the outcome produced by the listener, such as a saved audit record, a queued notification, or a collaborator invoked with the right data. If the goal is to test a listener in isolation, you can publish the event directly in the test and verify the listener's effect.

Do not conclude that a listener ran successfully simply because `applicationEvents.stream(...).count()` returned the expected number.

## 7. Situations Requiring Attention

### Asynchronous Event Listeners

Listeners run synchronously on the publishing thread by default unless configured to run asynchronously, such as with `@Async` alongside async support configuration. With an asynchronous listener, the test may see the published event before the listener finishes. When checking listener side effects, wait for completion using a bounded-time waiting mechanism; avoid fixed `Thread.sleep()` calls because they make tests slow and flaky.

### Listeners Bound to a Transaction

`@TransactionalEventListener` may handle an event only in a specific transaction phase, typically `AFTER_COMMIT`. If a test runs in a transaction that rolls back at the end of the test, a listener waiting for commit may never be invoked. Design the test so the transaction actually commits when testing post-commit behavior. Seeing an event in the recorder does not prove that the transaction committed or that the post-commit listener ran.

### Multiple Events of the Same Type

Do not blindly assert `hasSize(1)` when business logic can publish multiple events. Verify the list of payloads or stable identifiers to know which events appeared. Conversely, if the contract requires exactly one event, checking the exact count helps detect duplicate publications.

### Framework Events Appearing in the Context

The application context may publish Spring lifecycle or infrastructure events. Avoid counting all events and assuming they all belong to the business flow under test. Filter by the event type or payload type you want to verify.

### Comparing Data

For `BigDecimal`, prefer value-based assertions such as `isEqualByComparingTo` when scale is not part of the contract. For complex payloads, prefer checking key business fields rather than relying on `toString()` or an object's internal representation.

## 8. Process for Choosing Appropriate Assertions

| Testing Goal | Recording Approach | Required Assertion |
|---|---|---|
| Right event type was published | `stream(EventType.class)` | List contains the expected event |
| Payload is correct | Retrieve the event and read its fields; for plain objects, read `PayloadApplicationEvent.getPayload()` | Compare business fields |
| Published exactly once | Count the stream by event type | Count equals `1` |
| No unintended event published | Count the stream for that event type | Count equals `0` |
| Listener processed successfully | Check listener outcome or collaborator | Expected business effect occurred |
| Asynchronous listener completed | Wait for completion condition with a timeout | Effect appears before the timeout |

When writing a test, start from the operation's contract: which event it must publish, what data it must carry, and how many times it must be published. Then choose the corresponding query from `ApplicationEvents`. This approach helps tests clearly catch three common error categories: wrong event type, wrong payload, and wrong occurrence count.

## 9. Key Takeaways

`@RecordApplicationEvents` enables event recording for Spring TestContext tests; `ApplicationEvents` provides streams to filter and count events. For classes extending `ApplicationEvent`, query directly by that class type. For plain objects or records, inspect `PayloadApplicationEvent` and extract the payload. Finally, always distinguish between **an event being published** and **a listener processing it successfully**: these two facts require separate assertions.
