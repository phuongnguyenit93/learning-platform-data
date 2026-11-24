# Test Execution Events vs. Business Events

In a Spring application, both the testing framework and business code can publish events via `ApplicationContext` and handle them with `@EventListener`. Because both use Spring's event mechanism, the two kinds are easily confused. However, they express completely different things:

- A **test execution event** describes a milestone in the test execution lifecycle, such as Spring preparing a test instance or being about to invoke a `@Test` method.
- A **business/domain event** describes an occurrence meaningful to the business, such as an order having been created or a payment having been confirmed.

The most important distinction is **who publishes the event and what the event is about**. Events may travel across the same Spring event bus while belonging to two different contexts.

## 1. What Is a Test Execution Event?

The Spring TestContext Framework manages integration between test frameworks like JUnit and Spring features such as dependency injection, `ApplicationContext`, test transactions, or context management. During that process, Spring invokes `TestExecutionListener` callbacks at defined points in the test lifecycle.

`TestExecutionListener` receives a `TestContext` object, through which it can access information about the current test run, such as:

- The test class and test method currently running.
- Whether the test instance has been created and prepared.
- The `ApplicationContext` associated with the test.
- Any exception thrown during the test, if present.
- Temporary attributes attached to the `TestContext`.

These callbacks are hooks for **test infrastructure**. They are useful when setting up state, recording timings, collecting diagnostics, or cleaning up resources around test execution.

Spring defines the following main callbacks:

| Callback | Timing and Purpose |
|---|---|
| `beforeTestClass` | Before test methods in a class begin running. |
| `prepareTestInstance` | After the test instance is created; Spring can perform dependency injection and prepare the instance. |
| `beforeTestMethod` | Before `@BeforeEach` lifecycle methods and before executing the test method. |
| `beforeTestExecution` | Immediately before the `@Test` method body, after `@BeforeEach` methods. |
| `afterTestExecution` | Immediately after the `@Test` method body, before `@AfterEach` methods. |
| `afterTestMethod` | After `@AfterEach` methods, once the test method run has finished. |
| `afterTestClass` | After all test methods of the class have finished. |

With JUnit Jupiter, the general sequence around a test method is:

```text
Create test instance
    ↓
prepareTestInstance
    ↓
beforeTestMethod
    ↓
@BeforeEach
    ↓
beforeTestExecution
    ↓
@Test
    ↓
afterTestExecution
    ↓
@AfterEach
    ↓
afterTestMethod
```

At the class level, `beforeTestClass` and `afterTestClass` surround the test runs of the class. Integration details can depend on the test framework and extensions in use, yet the difference between `beforeTestMethod` and `beforeTestExecution` remains very useful: the former includes test method preparation, whereas the latter marks the moment right before the test body starts.

For example, to measure only the execution time of the `@Test` method body, start timing at `beforeTestExecution` and stop at `afterTestExecution`. Measuring from `beforeTestMethod` to `afterTestMethod` would also include test method setup and teardown.

## 2. From TestExecutionListener Callbacks to Test Execution Events

There are two common ways to react to the test lifecycle:

1. Implement `TestExecutionListener` directly and override the needed callbacks.
2. Listen for events that Spring publishes into the `ApplicationContext` corresponding to those callbacks.

Since Spring Framework 5.2, `EventPublishingTestExecutionListener` provides the second approach. This listener translates TestContext callbacks into strongly typed events and publishes them into the test's `ApplicationContext`. Common events include:

| Event | Corresponding Callback |
|---|---|
| `BeforeTestClassEvent` | `beforeTestClass` |
| `PrepareTestInstanceEvent` | `prepareTestInstance` |
| `BeforeTestMethodEvent` | `beforeTestMethod` |
| `BeforeTestExecutionEvent` | `beforeTestExecution` |
| `AfterTestExecutionEvent` | `afterTestExecution` |
| `AfterTestMethodEvent` | `afterTestMethod` |
| `AfterTestClassEvent` | `afterTestClass` |

In the default TestContext configuration, Spring registers `EventPublishingTestExecutionListener`. Therefore, when a test uses a Spring `ApplicationContext`, a bean can subscribe to these events with `@EventListener`.

Example: logging right before the test body executes.

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.event.BeforeTestExecutionEvent;

@Component
class TestLifecycleLogger {

    @EventListener
    void onBeforeTestExecution(BeforeTestExecutionEvent event) {
        TestContext testContext = event.getTestContext();

        System.out.printf(
            "Starting %s#%s%n",
            testContext.getTestClass().getSimpleName(),
            testContext.getTestMethod().getName()
        );
    }
}
```

The `TestLifecycleLogger` bean must be registered in the `ApplicationContext` used by the test, such as via component scanning or `@Import`. The event carries `TestContext`, so the listener can inspect the currently running test class and test method.

If you need to work directly with callbacks, you can write a `TestExecutionListener`. The following example stores the start timestamp in `TestContext` and computes elapsed time in the ending callback:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestExecutionListener;

public class TestBodyTimer implements TestExecutionListener {

    private static final String START_TIME =
        TestBodyTimer.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Long start = (Long) testContext.removeAttribute(START_TIME);
        if (start == null) {
            return;
        }

        long elapsedNanos = System.nanoTime() - start;
        System.out.printf(
            "%s#%s took %d ms%n",
            testContext.getTestClass().getSimpleName(),
            testContext.getTestMethod().getName(),
            elapsedNanos / 1_000_000
        );
    }
}
```

Registering the custom listener on a test class while preserving Spring's default listeners:

```java
@SpringJUnitConfig(TestConfig.class)
@TestExecutionListeners(
    listeners = TestBodyTimer.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
    // Test methods
}
```

`MERGE_WITH_DEFAULTS` is important when adding a custom listener while keeping the default listeners, including the listeners supporting Spring's integration and event publishing.

## 3. What Is a Business Event?

A business event describes a fact or state change meaningful in the business domain. For example:

- `OrderPlaced`: a customer placed an order.
- `PaymentConfirmed`: a payment was confirmed.
- `AccountLocked`: an account was locked under a business rule.

This kind of event is emitted by application logic when a business action occurs. In Spring, application code commonly uses `ApplicationEventPublisher` to announce the event; listeners can use `@EventListener` or `@TransactionalEventListener` to handle it.

Example of an order event:

```java
import java.util.UUID;

public record OrderPlaced(UUID orderId) {
}
```

Service publishing the event after saving the order:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    OrderService(
        OrderRepository orderRepository,
        ApplicationEventPublisher eventPublisher
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void placeOrder(Order order) {
        Order savedOrder = orderRepository.save(order);
        eventPublisher.publishEvent(new OrderPlaced(savedOrder.getId()));
    }
}
```

Another component can receive the event to perform related work:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class InventoryListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderPlaced(OrderPlaced event) {
        // Perform inventory business logic after the order creation transaction commits.
    }
}
```

`@TransactionalEventListener` lets you bind event handling to a transaction phase. In the example, the listener only runs after the transaction commits successfully. This makes business sense: the system should not update inventory for an order whose creation transaction rolled back.

`OrderPlaced` does not depend on JUnit or Spring TestContext. This event still has meaning when the real application runs, even when no tests are executing.

## 4. Comparing the Two Event Types

| Criterion | Test Execution Event | Business Event |
|---|---|---|
| Producer | Spring TestContext Framework via `TestExecutionListener` and `EventPublishingTestExecutionListener`. | Service, domain model, or application component when a business occurrence happens. |
| Meaning | Describes test run progress: preparing an instance, starting a test method, ending a test method. | Describes a business fact: order placed, payment confirmed. |
| Lifecycle | Tied to test execution and test classes. | Tied to application behavior, independent of whether tests are running. |
| Core Data | `TestContext`, test class, test method, test instance, and test execution details. | Necessary business data such as order ID, transaction ID, or changed state. |
| Typical Consumers | Test infrastructure, test-support listeners, logging, or test timing measurement. | Business components, post-event handlers, or integration with other systems. |
| When It Occurs | When Spring TestContext runs the corresponding callbacks and publishes events to the context. | When application logic actively publishes an event due to a business action. |
| Should It Be Used in Production? | No. This mechanism belongs to test infrastructure. | Yes, when that event is part of the application's design. |

An easily missed distinction: a test execution event can be published into the `ApplicationContext`, yet that does not turn it into a business event. `ApplicationContext` is merely the transport and dispatch mechanism. An event's meaning is determined by its event type, its producer, and when it is emitted.

## 5. Testing Business Events with Spring Test

When writing tests for `OrderService`, the goal is usually to confirm that placing an order emits the expected `OrderPlaced` event. We are testing the application's contract, not testing the `beforeTestExecution` callback.

Spring provides `@RecordApplicationEvents` and `ApplicationEvents` to record events published during test execution. You can use them to verify events by type:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        orderService.placeOrder(new Order(/* test data */));

        assertThat(events.stream(OrderPlaced.class)).hasSize(1);
    }
}
```

`ApplicationEvents` lets you filter events by type so the test stays focused on the contract to verify. In real tests, also check important event contents, such as `orderId`, instead of only counting occurrences.

Note that `ApplicationEvents` records events published into the context; recording an event does not prove every listener finished processing or that secondary data changes were committed. If you need to verify `@TransactionalEventListener` behavior, design the test around transaction boundaries and commit/rollback timing.

## 6. Choosing the Right Mechanism for Each Purpose

| Requirement | Appropriate Mechanism |
|---|---|
| Log before the test body runs | `BeforeTestExecutionEvent` or `TestExecutionListener.beforeTestExecution`. |
| Measure only the test body duration | `beforeTestExecution` and `afterTestExecution` pair. |
| Prepare shared data or resources around each test | `TestExecutionListener`, or JUnit/Spring lifecycle annotations matching the required scope. |
| Verify a service emits `OrderPlaced` | `@RecordApplicationEvents` and `ApplicationEvents`, or a separately configured test listener. |
| Perform work after an order is created | Business event such as `OrderPlaced` and an application listener. |
| Process only when the transaction has committed | `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. |

A few rules help avoid confusion:

1. **Do not use test execution events to represent business logic.** `AfterTestMethodEvent` only states that a test method ended; it does not mean an order, payment, or transaction in the application completed.
2. **Do not put production logic into listeners that exist only for tests.** If an action must happen when `OrderPlaced` is published, emit and handle the business event directly in the application design.
3. **Choose callbacks matching the exact phase you want to observe.** `beforeTestMethod` and `afterTestMethod` surround setup/teardown; `beforeTestExecution` and `afterTestExecution` wrap the test method body closely.
4. **Do not assume `@EventListener` implies a business event.** This annotation handles events in `ApplicationContext`; the listened event may be a test event, a technical event, or a business event.
5. **Separate test goals.** One test can verify that the application emits the right business event; another test can verify test-timing infrastructure. Both may share Spring's event mechanism without mixing their semantics.

When reading an event in a Spring application, identify its producer first: if the event is created by TestContext around `@Test`, it is a test execution event; if the event is created by application logic to express a business fact, it is a business/domain event. This classification helps you choose the right listener, processing timing, and test scope.
