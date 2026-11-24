# Filtering Infrastructure Events to Focus on the Business Contract

When testing a Spring component that publishes events, the goal is usually to verify that a business action emitted the right event, with the right data, and the expected number of times. However, an `ApplicationContext` can publish many kinds of events throughout its lifecycle. Beyond events created by business logic, a test may also encounter events describing Spring's state, request lifecycle, or other technical activities.

If a test checks the total number of events in the context, it becomes coupled to details outside the business contract. A more stable approach is to query the exact event type to verify using `ApplicationEvents.stream(Class<T>)`, or group business events through a common application-defined type. This filtering only narrows the data the test observes; it does not alter how events are published or dispatched in the application.

## 1. Distinguishing Business Events and Infrastructure Events

Spring provides a publish/subscribe mechanism via `ApplicationEventPublisher` and listeners in the `ApplicationContext`. An event can be a class extending `ApplicationEvent`, or any object published as a payload. Spring converts eligible payloads into `PayloadApplicationEvent` to route them through the common event mechanism.

The two event groups serve different purposes:

| Group | What the Event Describes | Examples |
|---|---|---|
| Business | A fact or outcome meaningful to the application's domain rules | `OrderPlaced`, `PaymentAuthorized`, `InventoryReserved` |
| Infrastructure | Runtime environment state or technical activity | `ContextRefreshedEvent`, `ContextClosedEvent`, `RequestHandledEvent` |

Business events generally answer the question "what happened in the business domain?". Event names should describe a fact that occurred, such as `OrderPlaced`, rather than a technical command like `SaveOrderCommand`. The payload should contain the data consumers need to understand the event, such as the order ID and total amount; avoid putting infrastructure dependencies like `HttpServletRequest`, `EntityManager`, or repositories into the contract.

Infrastructure events are still useful. A listener may need to react when the context is refreshed, or observability tooling may need to know when a request finished. However, those events are usually not what an `OrderService` test needs to verify. The test should focus on the business events the service commits to emitting.

## 2. Why Asserting the Full Event List Leads to Brittle Tests

Suppose a test calls `OrderService.placeOrder()` and then asserts that the context published only a single event:

```java
assertThat(applicationEvents.stream()).hasSize(1);
```

This assertion mixes two contracts:

- `OrderService`'s contract: when an order is placed successfully, the application emits `OrderPlaced`.
- A test environment detail: during that same period, no listener, Spring component, or auxiliary component emits any additional event.

The second contract can change whenever test configuration, libraries, listeners, or context initialization changes. The test could fail even though `OrderService` still does everything it is supposed to do.

For example, the context has lifecycle events such as `ContextRefreshedEvent` or request events such as `RequestHandledEvent`. They can appear in the same test environment without being the business outcome of placing an order. Checking the total event count couples the test to those events.

Instead, ask a narrow and clear question: "How many `OrderPlaced` events were published during this execution?".

## 3. Recording Events with `@RecordApplicationEvents`

The Spring TestContext Framework provides two components for observing events:

- `@RecordApplicationEvents`: instructs Spring to record events published in the `ApplicationContext` during the execution of a test.
- `ApplicationEvents`: the API for querying recorded events.

With JUnit Jupiter, `ApplicationEvents` can be declared as a parameter on a test method or lifecycle method. This is the appropriate style because the object is scoped per test method. Do not inject `ApplicationEvents` into the test class constructor.

The following example uses a record payload. `OrderPlaced` does not need to extend `ApplicationEvent`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(OrderServiceTests.TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Test
    void publishesOrderPlaced(
            @Autowired OrderService service,
            ApplicationEvents applicationEvents) {

        UUID orderId = UUID.randomUUID();
        BigDecimal total = new BigDecimal("125.00");

        service.placeOrder(orderId, total);

        List<OrderPlaced> published =
                applicationEvents.stream(OrderPlaced.class).toList();

        assertThat(published).hasSize(1);
        assertThat(published.get(0).orderId()).isEqualTo(orderId);
        assertThat(published.get(0).total()).isEqualByComparingTo("125.00");
    }

    @Configuration(proxyBeanMethods = false)
    @Import(OrderService.class)
    static class TestConfig {
    }
}

record OrderPlaced(UUID orderId, BigDecimal total) {
}

class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    void placeOrder(UUID orderId, BigDecimal total) {
        // Perform required business steps before publishing the event.
        eventPublisher.publishEvent(new OrderPlaced(orderId, total));
    }
}
```

`@SpringJUnitConfig` activates Spring TestContext for JUnit Jupiter and loads the test configuration. `@RecordApplicationEvents` enables the event recorder. The `ApplicationEvents` parameter is supplied by Spring for the current test. After calling the service, `stream(OrderPlaced.class)` returns only events or payloads of type `OrderPlaced`.

Thus, even if the context also records `ContextRefreshedEvent`, `RequestHandledEvent`, or another infrastructure event, the query above still focuses solely on `OrderPlaced` payloads. The test verifies both the count and the data of the business contract.

## 4. Choosing Filters Based on the Contract Under Test

### 4.1. Only One Event Type Needs Verification

Prefer querying directly by event type:

```java
List<OrderPlaced> orderEvents =
        applicationEvents.stream(OrderPlaced.class).toList();

assertThat(orderEvents).hasSize(1);
assertThat(orderEvents.get(0).orderId()).isEqualTo(expectedOrderId);
```

`stream(Class<T>)` accepts either an event type or a payload type. This is helpful when the application publishes records or POJOs, because the test does not need to unwrap `PayloadApplicationEvent` manually.

If a business branch must not publish an event, check that event directly:

```java
assertThat(applicationEvents.stream(OrderPlaced.class)).isEmpty();
```

This assertion clearly expresses what needs to be protected: in the current scenario, no order was successfully placed.

### 4.2. Multiple Business Events Belong to One Group

When multiple events need to be observed as a group, the application can define a marker interface. This is an application domain convention, not a Spring-mandated interface:

```java
interface BusinessEvent {
}

record OrderPlaced(UUID orderId) implements BusinessEvent {
}

record PaymentAuthorized(UUID orderId, String authorizationId)
        implements BusinessEvent {
}
```

The test can query the entire group by the common type:

```java
List<BusinessEvent> businessEvents =
        applicationEvents.stream(BusinessEvent.class).toList();

assertThat(businessEvents).hasSize(2);
assertThat(businessEvents)
        .anyMatch(OrderPlaced.class::isInstance)
        .anyMatch(PaymentAuthorized.class::isInstance);
```

Because `ApplicationEvents.stream(Class<T>)` supports both events and payloads matching the requested type, the marker interface can be implemented by business payloads. Spring's infrastructure events do not implement that marker interface, so they do not appear in this list.

Only add a marker interface when the event group is genuinely meaningful in the application design. If a test only needs to check `OrderPlaced`, querying `OrderPlaced.class` directly is simpler and more precise.

### 4.3. Filtering by Event Data

After filtering by type, you can filter further by business attributes:

```java
List<OrderPlaced> highValueOrders = applicationEvents
        .stream(OrderPlaced.class)
        .filter(event -> event.total().compareTo(new BigDecimal("1000")) >= 0)
        .toList();
```

This is observation-side filtering in the test. It fits when a test needs to verify a subset of events matching a specific condition, though it should not turn into complex filtering duplicated across many tests. If multiple tests need to express the same contract, consider creating a small, domain-named helper.

## 5. When to Use the No-Argument `stream()`

`applicationEvents.stream()` returns all recorded `ApplicationEvent` instances. This API is useful when diagnosing why an event did not appear, or when inspecting what types of events the context emitted during a test.

For example, you can list the types of recorded events while debugging:

```java
applicationEvents.stream()
        .map(event -> event.getClass().getName())
        .forEach(System.out::println);
```

However, do not turn this list into a stable contract for a business service. In particular, avoid assertions like:

```java
assertThat(applicationEvents.stream()).hasSize(3);
```

unless the exact count and complete set of all events is a clearly defined requirement for that test. Most service tests only need to verify one or a few specific event types.

If an event is published as a POJO, Spring may represent it internally using `PayloadApplicationEvent`. Do not write tests that depend on this internal wrapper class. Use `stream(OrderPlaced.class)` to query payloads by their business type.

## 6. Test Filtering vs. Runtime Listener Filtering

These two operations serve different purposes:

| Operation | Where Applied | Effect |
|---|---|---|
| `applicationEvents.stream(OrderPlaced.class)` | Test | Only selects events/payloads to observe and assert on |
| Listener accepting a specific event type | Running application | Determines whether the listener receives and handles that event type |
| `@EventListener` condition | Running application | Determines whether the listener handles the event based on a method condition |
| `@TransactionalEventListener` | Running application | Ties listener execution timing to a transaction phase |

Filtering with `ApplicationEvents` does not prevent events from being published and does not prevent other listeners from receiving them. It simply keeps the test focused on what needs to be verified. Do not modify publishers or remove listeners from the context merely to make the event list shorter in a test.

If the requirement is that a listener only handles one event type, test the listener configuration or behavior. If the requirement is that a listener only runs after a transaction commits, test the appropriate transaction boundary and phase. Querying published events does not by itself prove that a listener completed processing.

## 7. Recording Scope and Situations Requiring Attention

### Lifecycle of `ApplicationEvents`

`ApplicationEvents` represents events published during the execution of a single test method. With JUnit Jupiter, accept it as a parameter on `@Test`, `@BeforeEach`, or `@AfterEach`:

```java
@Test
void verifiesOrderEvent(ApplicationEvents applicationEvents) {
    // Invoke the action under test and query events here.
}
```

Do not inject `ApplicationEvents` into the test class constructor because this object only exists within the lifecycle of the current test method.

If `@BeforeEach` or another setup step also publishes events, those events can add noise to the test's observations. You can structure the test so the action under test begins after setup, or call `applicationEvents.clear()` at a clear boundary before performing the action:

```java
applicationEvents.clear();
service.placeOrder(orderId, total);

assertThat(applicationEvents.stream(OrderPlaced.class)).hasSize(1);
```

`clear()` clears events recorded prior to the call; subsequent queries only see events recorded afterward. There is no need to call `clear()` routinely in every test because the recorder is already managed per test method.

### TestExecutionListener Configuration

Spring registers `ApplicationEventsTestExecutionListener` by default. If a test declares `@TestExecutionListeners` and replaces the default listener list, ensure the application events recording listener remains registered. Without this listener, adding `@RecordApplicationEvents` may not provide the expected data.

### Transaction-Bound Events

`ApplicationEvents` records event publication. That differs from whether a `@TransactionalEventListener` ran in the desired phase. For example, an `AFTER_COMMIT` listener only executes after the transaction commits. A test running inside a transaction that rolls back by default may not produce the commit needed for the listener to run.

When testing post-commit behavior, establish an appropriate transaction boundary and verify the outcome on the listener or receiving system side. Do not infer that the listener ran merely because `stream(OrderPlaced.class)` returned an event.

### Asynchronous Events

If the application configures event handling with an executor, the time a listener completes may differ from when the publisher returns. Wait for an observable listener condition before asserting on asynchronous results. Do not assume asynchronous listeners complete in publication order unless the application guarantees that ordering and the contract requires testing it.

## 8. Testing Practices to Avoid

| Practice | Problem | Better Expression |
|---|---|---|
| Counting all events in the context | Coupled to infrastructure events and test configuration | Count `stream(OrderPlaced.class)` |
| Comparing the full event list to a fixed list | Breaks easily when adding listeners or Spring components | Check only events belonging to the business contract |
| Filtering by package or class name strings | Easily misses events when refactoring packages/classes | Query by event type or marker interface |
| Checking `PayloadApplicationEvent` as a mandatory detail | Coupled to how Spring wraps payloads | Query the payload directly with `stream(Class<T>)` |
| Assuming a published event means listeners finished processing | Ignores transaction phases and async execution | Test publication and listener processing outcomes separately |
| Adding runtime conditions just to reduce events in tests | Alters application behavior for test observation needs | Filter via `ApplicationEvents` in the test |

A good test describes behavior in business language. For example, "a valid order publishes exactly one `OrderPlaced`" is clearer and more resilient than "the context publishes one event in total".

## 9. Process for Choosing a Filter

When writing tests for an event flow, you can follow this sequence:

1. Identify the business fact the action must announce, such as `OrderPlaced`.
2. Enable `@RecordApplicationEvents` on the test class.
3. Receive `ApplicationEvents` in the test method.
4. Query directly with `stream(OrderPlaced.class)`.
5. Check the count and the data fields meaningful to event consumers.
6. If multiple events genuinely form a business group, consider a marker interface and query by the common type.
7. Use the full `stream()` only for diagnostics, not total event count as a default assertion.
8. If requirements involve listeners, transactions, or async execution, test behavior separately at the corresponding boundary.

## 10. References

- [Spring Framework Reference — Application Events in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): how to enable event recording and query with `ApplicationEvents`.
- [Spring Framework Reference — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html): scope and usage of the annotation.
- [Spring Framework Javadoc — `ApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html): signatures of `stream()`, `stream(Class<T>)`, and `clear()`.

The core idea of this technique is to let the test observe the exact contract published by the business component. Filter by business event or payload type before asserting; let infrastructure events continue serving Spring's lifecycle and technical operations without dominating service test results.
