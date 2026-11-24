# @RecordApplicationEvents and ApplicationEvents

Spring Framework provides an application event mechanism so components in an application can announce an event without directly calling each interested component. When testing, sometimes what needs to be verified is precisely that an operation emitted the right event, of the right type, carrying the right data. Spring Test provides `@RecordApplicationEvents` and `ApplicationEvents` to do that directly inside the test context.

This application event recording feature has been available since Spring Framework 5.3. The examples below use JUnit Jupiter and the Spring TestContext Framework.

## 1. What Do the Two Components Do?

- `@RecordApplicationEvents` is placed on a test class to enable recording of application events published during the execution of each test method.
- `ApplicationEvents` is the API that allows a test to read the recorded events. The API provides streams to retrieve all events or filter by event type.

The two components work together: the annotation enables the recording mechanism; the `ApplicationEvents` object provides the data for assertions. They do not publish events themselves and do not replace listeners in the application.

## 2. Reviewing the Application Event Mechanism

One component can publish an event through `ApplicationEventPublisher`. Another component in the same application context can receive the event using `ApplicationListener` or an `@EventListener` method.

For example, an order-processing service can emit `OrderSubmitted` after receiving an order. Another listener can use that event to write an audit record or send a notification. The order-processing service does not need to know which listeners are registered.

```java
public class OrderSubmitted extends ApplicationEvent {

    private final String orderId;

    public OrderSubmitted(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Service publishing the event:

```java
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void submit(String orderId) {
        // Perform order processing here.
        eventPublisher.publishEvent(new OrderSubmitted(this, orderId));
    }
}
```

Spring also allows publishing an arbitrary object with `publishEvent(Object)`. For an object that does not extend `ApplicationEvent`, Spring wraps that object in a `PayloadApplicationEvent` before dispatching it.

## 3. Enabling Recording with @RecordApplicationEvents

Place the annotation on a test class that uses Spring TestContext:

```java
@SpringJUnitConfig(OrderServiceTests.Config.class)
@RecordApplicationEvents
class OrderServiceTests {
    // Dependencies and test methods go here.
}
```

In this example:

- `@SpringJUnitConfig` configures Spring TestContext for JUnit Jupiter. This annotation combines loading the application context and integrating `SpringExtension`.
- `@RecordApplicationEvents` instructs Spring Test to record application events during the execution of the class's test methods.
- `ApplicationEvents` can be injected into the test class with `@Autowired`.

If using Spring Boot, `@RecordApplicationEvents` can be placed alongside `@SpringBootTest`. With other JUnit Jupiter configurations, ensure the test runs through Spring TestContext, such as via `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`.

Typically there is no need to manually register a test execution listener for this feature; Spring TestContext handles recording when the annotation is declared.

## 4. Reading Events with ApplicationEvents

Complete test example:

```java
import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderServiceTests.Config.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void recordsEventPublishedWhenOrderIsSubmitted() {
        orderService.submit("A-42");

        List<OrderSubmitted> publishedEvents = applicationEvents
                .stream(OrderSubmitted.class)
                .collect(Collectors.toList());

        assertEquals(1, publishedEvents.size());
        assertEquals("A-42", publishedEvents.get(0).getOrderId());
    }

    @Configuration
    static class Config {

        @Bean
        OrderService orderService(ApplicationEventPublisher eventPublisher) {
            return new OrderService(eventPublisher);
        }
    }
}
```

The test flow proceeds as follows:

1. Spring creates the application context for the test class and enables event recording.
2. The test calls `orderService.submit("A-42")`.
3. `OrderService` publishes an `OrderSubmitted` into the application context.
4. `ApplicationEvents` provides the recorded events of type `OrderSubmitted`.
5. The test checks the number of events and the `orderId` value.

`stream(OrderSubmitted.class)` returns a stream already filtered by event type. This approach is usually clearer than retrieving all events and checking types manually with `instanceof`.

## 5. Common Query Patterns

`ApplicationEvents` provides `stream()` to iterate over all events and `stream(Class<T>)` to retrieve events by type. Because the result is a Java Stream, familiar Stream operations can be used.

Counting events:

```java
long count = applicationEvents.stream(OrderSubmitted.class).count();
assertEquals(1, count);
```

Checking whether an event matches a condition:

```java
boolean hasExpectedOrder = applicationEvents
        .stream(OrderSubmitted.class)
        .anyMatch(event -> "A-42".equals(event.getOrderId()));

assertEquals(true, hasExpectedOrder);
```

Getting the first event:

```java
OrderSubmitted event = applicationEvents
        .stream(OrderSubmitted.class)
        .findFirst()
        .orElseThrow(() -> new AssertionError("OrderSubmitted was not published"));

assertEquals("A-42", event.getOrderId());
```

Collecting all events to inspect multiple properties:

```java
List<OrderSubmitted> events = applicationEvents
        .stream(OrderSubmitted.class)
        .collect(Collectors.toList());
```

Each time you need to query, create a fresh stream from `ApplicationEvents`. A Java Stream can only be consumed once; do not store a stream and reuse it across multiple assertions.

## 6. Inspecting Payload Events

When the application publishes an object that does not extend `ApplicationEvent`, Spring represents it as a `PayloadApplicationEvent`. Therefore, if you need to inspect the payload, read the payload from the wrapper:

```java
List<Object> payloads = applicationEvents
        .stream(PayloadApplicationEvent.class)
        .map(PayloadApplicationEvent::getPayload)
        .collect(Collectors.toList());
```

Required import:

```java
import org.springframework.context.PayloadApplicationEvent;
```

If you only care about a specific payload, you can filter further by payload type or value. For event classes extending `ApplicationEvent`, querying directly with `stream(MyEvent.class)` is usually simpler.

## 7. Scope and Timing of Recording

Recording is tied to test method execution. Spring TestContext manages the lifecycle of event data per method, so events from one test should not be treated as shared data accumulated across multiple test methods.

A few consequences to keep in mind:

- Events published while a test method is running can be queried through that test's `ApplicationEvents`.
- Events emitted while the application context is initializing usually occur before the test method's recording phase, so this API should not be used to check context startup events.
- Query events within the corresponding test method where the event-emitting action is executed.
- If tests use multiple application contexts, ensure the action and the `ApplicationEvents` being inspected belong to the right context.

This mechanism records events published in the application context. It does not change how Spring dispatches events and does not execute listeners by itself.

## 8. Recording Events vs. Testing Listeners

There are two distinct testing questions:

1. **Did the component publish the right event?** Use `@RecordApplicationEvents` and `ApplicationEvents` to verify the event type, publication count, and event data.
2. **Did the listener handle the event properly?** Verify the result or side effect produced by the listener, such as an audit record, updated state, or an invocation on a collaborator.

Finding an event in `ApplicationEvents` proves the event was published and recorded in the context. That alone does not prove every listener processed it successfully. If a listener uses `@Async`, processing may complete after the publish call finishes; when testing asynchronous side effects, the test needs an appropriate waiting or synchronization mechanism.

## 9. When Should It Be Used?

This feature is useful when events are part of the contract of the component under test:

- A service must publish an event after completing a business operation.
- A command must emit exactly one event or emit no event when data is invalid.
- An event must carry the right object identifier, status, or business information.
- A processing flow emits multiple events and the test needs to confirm the important event appeared.

There is no need to record events in every test. If the goal is simply to verify a method's return value and events are not part of the behavior to guarantee, direct assertions on the result are usually easier to understand.

## 10. Common Pitfalls

| Symptom | Common Cause | How to Fix |
|---|---|---|
| No events appear in the stream | Missing `@RecordApplicationEvents` or the test is not running through Spring TestContext | Add the annotation and check the Spring test configuration |
| Stream lacks the expected event | The test has not invoked the publishing action or is querying the wrong event type | Verify the execution path and use the right event class |
| POJO event not found by payload class | Spring wraps the object in `PayloadApplicationEvent` | Query the wrapper and then call `getPayload()` |
| Test sees more events than expected | The context emits other events during the test | Filter by a specific event type and check business conditions |
| Event exists but listener has not produced a side effect | Checking publication instead of listener processing results; the listener may run asynchronously | Assert on listener results and wait for completion if needed |

## 11. Checklist When Writing Tests

- The test class uses Spring TestContext and has `@RecordApplicationEvents`.
- `ApplicationEvents` is injected from the right test context.
- The test performs the action capable of publishing the event before querying the stream.
- Assertions filter by a specific event class when possible.
- The test verifies both the count and the important data of the event.
- If listener verification is needed, the test checks listener side effects separately.
- Do not retain or reuse a Java Stream after a terminal operation.

## 12. Key Takeaways

`@RecordApplicationEvents` enables application event recording in Spring TestContext for each test method. `ApplicationEvents` lets you query those events using Java Streams. Combining these two APIs helps tests verify that an operation published the right event with the right data, while keeping a clear boundary between testing event publication and testing listener processing logic.

