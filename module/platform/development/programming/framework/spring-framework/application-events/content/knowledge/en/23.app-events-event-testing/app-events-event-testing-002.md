# Mocking ApplicationEventPublisher in Spring Application Events Testing

## 1. Why Mock ApplicationEventPublisher?

In a Spring application, a use case may persist state and then emit a business event so other components can react:

~~~text
PlaceOrder command
        |
        v
   OrderService
       |             +---------------------+
       +-- save ---->| OrderRepository     |
       |             +---------------------+
       |
       +-- publish --> OrderPlaced
                           |
                           +--> AuditListener
                           +--> EmailListener
                           +--> SearchProjectionListener
~~~

When testing `OrderService` in isolation, the goal is usually to confirm:

- With valid input, the service persists the right data.
- The service emits the **right event type** and **right payload**.
- The ordering between save and publish matches the application service layer's contract.
- With invalid input or a direct persistence failure, the service **does not emit a success event**.
- No extra or unintended duplicate emissions occur.

We **do not need to start a real ApplicationContext** to verify those calls. Instead, pass an `ApplicationEventPublisher` mock created with Mockito into the service constructor, invoke the method under test, and then use `verify(...)` and `ArgumentCaptor`.

**Very important limitation:** mocking proves **the call to the publisher**, not that Spring's multicaster dispatched the event, listeners ran, the transaction committed, or work was delivered durably. Those requirements need corresponding integration tests or contract tests.

This lesson belongs to the **Event Testing** group of Spring Framework Application Events. The focus is on mocking `ApplicationEventPublisher` properly with Mockito, not a general introduction to Mockito.

## 2. ApplicationEventPublisher Is the Right Boundary for Unit Tests

`ApplicationEventPublisher` is the interface provided by Spring to publish events. Two important overloads:

~~~java
void publishEvent(Object event);
void publishEvent(ApplicationEvent event); // default overload
~~~

Spring Framework allows publishing a plain object, including a Java `record`, since Spring 4.2. For an object that does not extend `ApplicationEvent`, the context implementation can wrap the payload in `PayloadApplicationEvent` for internal handling. Therefore, a domain event **does not have to** extend `ApplicationEvent`.

A testable service should receive the publisher via **constructor injection**:

~~~java
public final class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }
}
~~~

The snippet above only illustrates the class members; the full file appears in section 5. Because dependencies are passed in from outside, a unit test can instantiate the object with `new OrderService(mockRepository, mockPublisher)`. The Spring container, bean scanning, multicaster, real database, and real listeners **do not need to be started**.

This keeps tests fast, narrow in scope, and produces clear failure messages. The test does not test framework APIs; it checks that our application code uses the API as intended.

### 2.1. Which Contracts Should Be Tested?

| Use Case Contract | Verifiable by Unit Test with Mockito? |
| --- | --- |
| `publisher.publishEvent(...)` was called once | Yes |
| Event contains the right order ID, amount, and required info | Yes |
| Does not publish if input is invalid | Yes |
| Repository was called before publisher | Yes, using `InOrder` |
| Exception from repository prevents publishing | Yes, when simulating a repository call error |
| `@EventListener` actually receives the event | **No** with a mocked publisher |
| Event was processed in `AFTER_COMMIT` | **No** |
| Database transaction committed | **No** |
| Event went through the async executor properly | **No** |
| Event was durably written to an outbox/broker | **No** |

Do not judge a test's quality by the number of `verify` calls. What matters is that the test protects **contracts with business value** and avoids locking down implementation details that can change without altering the desired outcome.

## 3. Test Design Strategy: Arrange, Act, Assert

A publisher mock test typically consists of:

1. **Arrange:** create mocks for `OrderRepository` and `ApplicationEventPublisher`.
2. **Act:** invoke the business method on `OrderService`.
3. **Assert:** verify repository state/calls and that the right event was published.

Conceptual example:

~~~java
OrderRepository repository = mock(OrderRepository.class);
ApplicationEventPublisher publisher =
    mock(ApplicationEventPublisher.class);

OrderService service = new OrderService(repository, publisher);
service.place(101L, 12000L);

verify(publisher).publishEvent(new OrderPlaced(101L, 12000L));
~~~

This is **illustrative code inside a test method**. Mockito imports and the types `OrderService`, `OrderRepository`, and `OrderPlaced` are required. Section 5 provides a complete Java 17+ project with Maven and runnable tests.

Mockito records invocations on the interface. Because `OrderPlaced` is a Java `record`, `equals/hashCode` based on its components are automatically generated, so `verify(publisher).publishEvent(new OrderPlaced(...))` can compare contents intuitively.

If an event is a mutable object without a proper `equals`, direct comparison with a new instance can fail even when fields match. In that case use `ArgumentCaptor` or matchers for the right fields, though by design immutable event payloads should be preferred.

## 4. Why Not Mock the Entire Spring Context in a Unit Test?

There are several ways to supply event publishing to code: inject `ApplicationEventPublisher`, inject `ApplicationContext`, or call a dedicated event-emitting wrapper service. For unit testing a plain service, injecting the narrow `ApplicationEventPublisher` interface is usually better than injecting the broad `ApplicationContext` with many unrelated capabilities.

### No Need to Start a Context Just to Verify One Call

If a test only needs to verify `publishEvent`, starting `AnnotationConfigApplicationContext` or `@SpringJUnitConfig` makes the test depend on bean scanning, configuration, lifecycle, proxies, and listeners outside the test's scope.

Direct mocking pattern:

~~~text
JUnit test
   |
   +-- Mockito.mock(OrderRepository.class)
   +-- Mockito.mock(ApplicationEventPublisher.class)
   |
   +-- new OrderService(repository, publisher)
   |
   +-- service.place(...)
   |
   +-- verify(...) / capture(...)
~~~

**Benefits:** fast, runs independently, clear failures, and no `@SpringBootTest` needed. However, when you want to verify **whether the event is actually dispatched by Spring**, use an integration test with a real context (section 7).

### Why Not Replace the Context's Publisher with a Mock?

In a Spring integration test, if you replace `ApplicationEventPublisher` with a Mockito mock, calls to the mock do not automatically go through the multicaster. This can let a "publish was called" test PASS even when listeners never run at all. Moreover, replacing core Spring beans can alter context/lifecycle behavior.

When an integration test needs to prove listeners run, **keep the real publisher** and record events with `@RecordApplicationEvents`/`ApplicationEvents`, or spy on the listener/measure outcomes. Avoid mocking the publisher when what you want to verify is the dispatch mechanism itself.

## 5. Runnable Java 17+ Project: Unit Testing with Mockito

The following project does not require Spring Boot. It uses:

- Spring Framework 6.2.8 for `ApplicationEventPublisher` and `@EventListener`.
- JUnit Jupiter 5.11.4 for writing tests.
- Mockito 5.15.2 for creating mocks, `verify`, `InOrder`, and `ArgumentCaptor`.
- Spring Test 6.2.8 for running an integration test with the event recorder.
- Maven Surefire 3.5.2 for running JUnit 5 via `mvn test`.

### 5.1. Directory Structure

~~~text
event-publisher-testing/
├── pom.xml
└── src
    ├── main
    │   └── java/example/events
    │       ├── Order.java
    │       ├── OrderPlaced.java
    │       ├── OrderRepository.java
    │       └── OrderService.java
    └── test
        └── java/example/events
            ├── OrderServiceTest.java
            └── RecordingIntegrationTest.java
~~~

Each public class resides in a matching file under `package example.events`. The two test classes have **distinct** responsibilities: `OrderServiceTest` tests the mocked publisher, and `RecordingIntegrationTest` tests real Spring dispatch.

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-publisher-testing</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.15.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. Domain Object: Order.java

~~~java
package example.events;

public record Order(long id, long totalCents) { }
~~~

In the example, `Order` stores an ID and total amount as integer cents. This is a simplified model for testing, not a full financial design pattern (no currency, decimal rounding, state transitions, etc.).

### 5.4. Event Payload: OrderPlaced.java

~~~java
package example.events;

public record OrderPlaced(long orderId, long totalCents) { }
~~~

`OrderPlaced` is a **fact** published after the repository accepts the save call. Being a record, it has value-based `equals`, which is very convenient for Mockito assertions. It **does not extend ApplicationEvent**, so publishing it through the publisher selects the `publishEvent(Object)` overload.

### 5.5. Repository Port: OrderRepository.java

~~~java
package example.events;

public interface OrderRepository {
    void save(Order order);
}
~~~

This is an application port, independent of any database. In unit tests, Mockito mocks this interface; in the dispatch integration test, a minimal in-memory implementation is used.

### 5.6. Use Case: OrderService.java

~~~java
package example.events;

import java.util.Objects;
import org.springframework.context.ApplicationEventPublisher;

public final class OrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = Objects.requireNonNull(repository);
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void place(long id, long totalCents) {
        if (id <= 0 || totalCents <= 0) {
            throw new IllegalArgumentException(
                "Order id and total must be positive"
            );
        }

        Order order = new Order(id, totalCents);
        repository.save(order);

        // Java record does not extend ApplicationEvent, so it selects
        // the publishEvent(Object) overload.
        publisher.publishEvent(
            new OrderPlaced(order.id(), order.totalCents())
        );
    }
}
~~~

This flow deliberately calls `repository.save` before `publishEvent`. When `save` throws an exception, the publish call is never executed. **However**, when a real repository is wrapped in a transaction, calling `save` does not guarantee the transaction has committed at the exact moment of publish. Transactions are analyzed in section 9.

## 6. Complete Unit Test: verify, ArgumentCaptor, InOrder, and Negative Cases

File `src/test/java/example/events/OrderServiceTest.java`:

~~~java
package example.events;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderServiceTest {

    // Each test method gets a new test class instance by JUnit default.
    private final OrderRepository repository =
        mock(OrderRepository.class);

    private final ApplicationEventPublisher publisher =
        mock(ApplicationEventPublisher.class);

    private final OrderService service =
        new OrderService(repository, publisher);

    @Test
    void validOrderPublishesExactlyOneCorrectEventAfterSave() {
        service.place(101L, 12_000L);

        InOrder calls = inOrder(repository, publisher);
        calls.verify(repository).save(new Order(101L, 12_000L));

        // Use an Object captor to check the right POJO overload.
        ArgumentCaptor<Object> eventCaptor =
            ArgumentCaptor.forClass(Object.class);

        calls.verify(publisher).publishEvent(
            eventCaptor.capture()
        );
        calls.verifyNoMoreInteractions();

        OrderPlaced event = assertInstanceOf(
            OrderPlaced.class, eventCaptor.getValue()
        );

        assertEquals(101L, event.orderId());
        assertEquals(12_000L, event.totalCents());
    }

    @Test
    void invalidOrderDoesNotSaveOrPublish() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.place(-1L, 12_000L)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> service.place(101L, 0L)
        );

        verifyNoInteractions(repository, publisher);
    }

    @Test
    void repositoryFailurePreventsPublishing() {
        doThrow(new IllegalStateException("storage down"))
            .when(repository).save(any(Order.class));

        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.place(101L, 12_000L)
        );

        assertEquals("storage down", error.getMessage());
        verify(repository).save(new Order(101L, 12_000L));
        verifyNoInteractions(publisher);
    }
}
~~~

### 6.1. What Does the First Test Prove?

- `service.place(...)` executes the success branch.
- `InOrder` verifies that `repository.save(new Order(...))` occurred **before** `publisher.publishEvent(...)`.
- `ArgumentCaptor<Object>` captures the object passed to the publisher.
- `assertInstanceOf(OrderPlaced.class, ...)` confirms the event type.
- Two `assertEquals` calls confirm the exact ID and amount.
- `calls.verifyNoMoreInteractions()` ensures no interactions occurred beyond those two verified calls, including no second publish.

Mockito does not run real listeners; it only captures invocations.

### 6.2. What Does the Second Test Prove?

Two invalid inputs are rejected before calling the repository and publisher. `verifyNoInteractions(repository, publisher)` ensures no side effects via either mocked dependency.

This is an important test for past-tense events like `OrderPlaced`: a rejected command **must not publish the fact "order was placed"**.

### 6.3. What Does the Third Test Prove?

Mockito configures `repository.save(...)` to throw `IllegalStateException`. Because the use case performs save before publish, the exception stops the method immediately and `publisher.publishEvent(...)` is never called.

**Do not over-infer:** this test simulates **save throwing an error immediately on invocation**; it does not simulate a transaction manager failing **at commit time after the method returns**. If commit fails later, the use case may already have called the publisher beforehand. Real transaction tests and after-commit/outbox policies are needed if the business requires them.

## 7. Integration Test: Using a Real Publisher and @RecordApplicationEvents

A unit test mocking the publisher can PASS even if the real system never registers a listener, misconfigures `@EventListener`, or mismatches event types. When you want to verify **real Spring dispatch**, use Spring TestContext instead of mocking the publisher.

Spring Framework provides:

- `@SpringJUnitConfig`: combines the JUnit Jupiter extension with Spring context configuration.
- `@RecordApplicationEvents`: enables recording application events within the scope of each test.
- `ApplicationEvents`: reads published events and filters by type via `events.stream(OrderPlaced.class)`.

### 7.1. RecordingIntegrationTest.java

File `src/test/java/example/events/RecordingIntegrationTest.java`:

~~~java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(RecordingIntegrationTest.Config.class)
@RecordApplicationEvents
class RecordingIntegrationTest {

    public static class CapturingListener {
        private final List<OrderPlaced> received =
            new CopyOnWriteArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
        }

        public List<OrderPlaced> received() {
            return List.copyOf(received);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        OrderRepository orderRepository() {
            // Simulate save only to test dispatch, no DB.
            return order -> { };
        }

        @Bean
        OrderService orderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(repository, publisher);
        }

        @Bean
        CapturingListener capturingListener() {
            return new CapturingListener();
        }
    }

    @Test
    void realSpringContextRecordsAndDispatchesEvent(
            @Autowired OrderService service,
            @Autowired CapturingListener listener,
            ApplicationEvents events
    ) {
        service.place(202L, 34_000L);

        assertEquals(
            1L,
            events.stream(OrderPlaced.class).count()
        );
        assertEquals(
            List.of(new OrderPlaced(202L, 34_000L)),
            listener.received()
        );
    }
}
~~~

### 7.2. Why Are Both Assertions Needed?

- `events.stream(OrderPlaced.class).count()` proves an event of type `OrderPlaced` was published and recorded by Spring TestContext within the test scope.
- `listener.received()` proves an `@EventListener` was actually registered by Spring **and processed the event** under the example's synchronous dispatch configuration.

Checking only `ApplicationEvents` does not prove a specific listener received it. Checking only the listener leaves the global event recording API unused. The two assertions complement each other.

**Note:** `@RecordApplicationEvents` records events within the test method scope and `ApplicationEvents` is accessed during the corresponding test lifecycle. It is not a production event store; filtering by `OrderPlaced.class` avoids counting other framework context events.

### 7.3. Running the Whole Project

From the `event-publisher-testing` directory:

~~~bash
mvn test
~~~

With the files above and an environment with JDK 17+, Maven, and dependencies downloaded successfully, **three unit tests and one integration test** are expected to PASS. Maven Surefire writes reports under `target/surefire-reports`.

~~~text
OrderServiceTest:
  validOrderPublishesExactlyOneCorrectEventAfterSave     PASS
  invalidOrderDoesNotSaveOrPublish                      PASS
  repositoryFailurePreventsPublishing                   PASS

RecordingIntegrationTest:
  realSpringContextRecordsAndDispatchesEvent            PASS

Total: 4 tests, 0 failures, 0 errors
~~~

The block above is an **expected outcome summary written for documentation**, not verbatim Maven stdout. Maven output can vary by plugin version and environment. If a test fails, inspect the stack trace/Surefire report; never alter assertions just to make a test green when the contract is broken.

## 8. An Important Java Trap: publishEvent Is Overloaded

`ApplicationEventPublisher` has an overload accepting `ApplicationEvent` and an overload accepting `Object`. The **static** Java type of the argument decides which overload the compiler selects.

With a Java record:

~~~java
public record OrderPlaced(long id) { }

publisher.publishEvent(new OrderPlaced(42L));
~~~

The record does not extend `ApplicationEvent`, so the compiler picks `publishEvent(Object)`. The corresponding Mockito verification:

~~~java
verify(publisher).publishEvent(
    new OrderPlaced(42L)
);
~~~

However, if you define an event type extending `ApplicationEvent`:

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {
    public OrderPlacedEvent(Object source) {
        super(source);
    }
}
~~~

Then the call:

~~~java
publisher.publishEvent(new OrderPlacedEvent(this));
~~~

typically selects the **ApplicationEvent overload** at compile time. On a plain Mockito mock, do not assume `verify(publisher).publishEvent(any(Object.class))` will inspect every overload the right way. You may need:

~~~java
verify(publisher).publishEvent(
    any(ApplicationEvent.class)
);
~~~

These snippets are **illustrative only** and require Mockito/Spring imports and appropriate context classes. If emitted as `(Object) event`, the compiler again picks the Object overload. When a test fails with "Wanted but not invoked", check the overload before concluding the service never published.

**Note on default methods:** on a real implementation, the `publishEvent(ApplicationEvent)` overload may delegate to `publishEvent(Object)`; on a Mockito mock, default method behavior is not necessarily executed like a real implementation. Test invocations against the **contract called by application code**, rather than inferring from an implementation's internal delegation path.

### 8.1. When to Use ArgumentCaptor<Object>?

`ArgumentCaptor<Object>` is a safe choice when a service emits POJO events and you want to inspect the runtime type. For example:

~~~java
ArgumentCaptor<Object> captor =
    ArgumentCaptor.forClass(Object.class);

verify(publisher).publishEvent(captor.capture());

OrderPlaced event =
    assertInstanceOf(OrderPlaced.class, captor.getValue());
assertEquals(42L, event.orderId());
~~~

If multiple publishes occur in the same method, use `captor.getAllValues()` and `verify(publisher, times(n))` according to the contract. Do not just read `getValue()` (which usually returns the last capture) and forget that other events might have been emitted.

## 9. Verifying Ordering and Emission Counts

### 9.1. Verifying Exactly Once

By default, `verify(mock).method(...)` requires the matching invocation to have happened **once**. You can make it explicit:

~~~java
verify(publisher, times(1)).publishEvent(
    new OrderPlaced(101L, 12_000L)
);
~~~

This is a test fragment requiring Mockito static imports `verify` and `times`. If policy permits other events, avoid overly broad `verifyNoMoreInteractions(publisher)`; explicitly specify which events and counts matter.

### 9.2. Not Publishing When a Command Is Rejected

~~~java
verifyNoInteractions(publisher);
~~~

This is a strong assertion: the publisher had **no interactions at all**. In an isolated unit test containing only the service under test, this makes sense. However, if the same mock is shared across setups or other calls, this assertion can fail due to interactions unrelated to the path under test.

A narrower check:

~~~java
verify(publisher, never()).publishEvent(
    any(OrderPlaced.class)
);
~~~

When the event is the POJO `OrderPlaced`, `any(OrderPlaced.class)` selects the Object overload, matching the event type in the example. For an event type extending `ApplicationEvent`, review the overload.

### 9.3. Testing Ordering with InOrder

~~~java
InOrder order = inOrder(repository, publisher);
order.verify(repository).save(expectedOrder);
order.verify(publisher).publishEvent(expectedEvent);
~~~

This ordering is useful if the design requires **not publishing the event before save is called**. However, it does not prove the event appears only **after DB commit**. Those are two different contracts.

### 9.4. Keeping Tests Non-Brittle

Do not verify every internal call if business logic only cares about an output fact. For example, refactoring a repository into two helpers can still preserve the publish contract. Overly detailed Mockito tests make refactoring expensive.

Right-sized testing advice: for application service tests, prioritize three things: **"right event, right payload, nothing emitted on failure"**. Only check `InOrder` when ordering is truly a use case invariant.

## 10. Mocking the Publisher Does Not Test Transactions and Rollback

A real-world use case may use:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = domainService.place(command);
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

This is **sketch code**, not part of the Maven demo project, because it requires `PlaceOrder`, domain service, repository, imports, and a concrete transaction manager.

In a normal transaction, `publishEvent(...)` is called **before the final commit point**. If the transaction rolls back afterward, a synchronous listener may already have received the event. Mockito `verify` still PASSES because it checks the invocation; it **does not know** whether the transaction committed.

### 10.1. When Listeners Should Run Only After Commit

Spring supports:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        notificationService.notify(event);
    }
}
~~~

This snippet is illustrative and requires importing `Component`, `TransactionalEventListener`, `TransactionPhase`, and the relevant beans/types.

`AFTER_COMMIT` ensures the listener runs when the transaction associated with the event commits successfully; if the transaction rolls back, this phase's listener does not run. If published outside a transaction, `@TransactionalEventListener` does not execute by default (unless `fallbackExecution=true` is configured). None of these behaviors are **proven** by a publisher mock.

To test phases, use an integration test with a real transaction manager, perform commit/rollback, and measure the listener's outcome. Note that `@Transactional` on the test method itself usually rolls back at the end of the test, so you must actively manage transaction boundaries before asserting after-commit events.

### 10.2. Do Not Equate Publish with Durable Delivery

Even with an `AFTER_COMMIT` listener, a process crash can lose work not yet delivered to an external system. When an event carries information that must be transmitted durably, consider a **transactional outbox**:

~~~text
Transaction T1:
    save order
    insert outbox event row (eventId, payload)
commit T1
    |
    v
dispatcher -> broker / external consumer
            retry + idempotency
~~~

A Mockito publisher mock does not test the outbox or retries. Those requirements need integration tests with a database, worker dispatcher, and failure scenarios.

## 11. Mocking the Publisher Does Not Test Async Listeners

Suppose a listener:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    emailService.send(event.orderId());
}
~~~

This is illustrative code requiring `@EnableAsync`, an executor, and corresponding beans. When a real publisher dispatches the event, Spring can run the listener on a worker thread. But a mocked publisher **does not schedule tasks** and does not invoke listeners, so a unit test with only `verify(publisher)` cannot know:

- Whether `@Async` is enabled.
- Whether the executor is configured properly.
- Whether the listener is running synchronously because proxying did not take effect.
- Whether worker errors are handled via `AsyncUncaughtExceptionHandler`.
- Whether scheduling/rejection errors are observed.
- Whether shutdown waits for tasks or cancels work per policy.

When you need to test async dispatch, use a real context with an observable listener; check results using `CountDownLatch`/futures/persistent state with a timeout. Never use `Thread.sleep(100)` and guess the task completed.

In an integration test using `@RecordApplicationEvents`, recording the event at publish time **does not mean async listeners have finished**. Assertions on async listeners must await the actual outcome. `events.stream(...)` only tells whether the event was recorded, not that every listener handled it successfully.

## 12. Mocking the Publisher and Testing Listeners Are Two Different Levels

Three tests typically complement each other:

### 12.1. Producer Unit Test

**System under test:** `OrderService`.

**Mocked dependencies:** `ApplicationEventPublisher` and `OrderRepository`.

**Assertion:** `OrderPlaced` is published accurately when logic accepts the order; not published on error paths.

This is the direct goal of this lesson.

### 12.2. Listener Unit Test

**System under test:** `OrderAuditListener` or `NotificationListener`.

Construct the event directly and call the listener method; mock the listener's dependencies such as `AuditRepository`/`EmailClient`. Test **the content of the listener's reaction**, without needing a publisher or Spring event dispatch if the method does not depend on container behavior.

For example:

~~~java
OrderPlaced event = new OrderPlaced(101L, 12_000L);
listener.onOrderPlaced(event);
verify(auditRepository).appendFor(101L, 12_000L);
~~~

This is an illustrative code snippet with `listener`/`auditRepository`. It does not test Spring listener registration, proxies, transaction phases, or async scheduling.

### 12.3. Event Dispatch Integration Test

**System under test:** Spring ApplicationContext + producer + listener.

Use a real publisher and `@RecordApplicationEvents`, a spy, or the listener's final state. Test that events flow through the framework as configured; add transaction/async integration tests when they are part of the contract.

The three test layers have different purposes and do not replace one another. Only write tests suited to the feature's risk rather than duplicating the same assertion at every level.

## 13. Simple Fake Publisher When Mockito Is Not Needed

Mockito helps with verify, capture, and exception stubbing. Yet `ApplicationEventPublisher` is a functional interface with a single abstract method accepting `Object`, so simple tests can use an **event-collecting fake**:

~~~java
List<Object> published = new ArrayList<>();

ApplicationEventPublisher fakePublisher =
    event -> published.add(event);

OrderService service =
    new OrderService(fakeRepository, fakePublisher);

service.place(101L, 12_000L);

assertEquals(
    List.of(new OrderPlaced(101L, 12_000L)),
    published
);
~~~

This is an illustrative test snippet: requires importing `List`, `ArrayList`, JUnit `assertEquals`, and a fake repository (e.g., an implementation that merely records data). A lambda is used instead of Mockito to store event objects.

**Difference:** a fake records data directly for inspection, whereas Mockito records invocations and offers `verify`/`ArgumentCaptor`/`InOrder`. A fake is handy when you want to read a list of events; Mockito is handy when there are multiple dependencies or ordering must be verified. Neither **dispatches** through a Spring context.

## 14. Mockito Matchers, ArgumentCaptor, and Common Pitfalls

### 14.1. Using Typed Matchers Properly

In simple cases:

~~~java
verify(publisher).publishEvent(
    argThat(event ->
        event instanceof OrderPlaced placed
        && placed.orderId() == 101L
        && placed.totalCents() == 12_000L
    )
);
~~~

This is a unit test fragment; Java 17 supports pattern matching for `instanceof`. `argThat` is a Mockito matcher. Because Java overloads exist, matcher type inference can make the call ambiguous in some cases. When running into overload issues, `ArgumentCaptor<Object>` and asserting the event type after capturing is usually clearer.

### 14.2. Do Not Mix Raw Values and Matchers Improperly

If a method has multiple parameters, once you use a matcher for one parameter, the remaining parameters must also be specified via appropriate matchers (e.g., `eq(...)`), without mixing in raw literals arbitrarily in a Mockito call. Since `publishEvent` takes only one parameter, this issue rarely appears here, though it still matters when testing other dependencies.

### 14.3. Do Not Mock Final Events Unnecessarily

An event record is a data value. Tests should construct a real `new OrderPlaced(...)` and inspect its contents. Mocking an event record undermines the contract because the test might only verify stubbed behavior of a fake object.

### 14.4. Capturing Arguments and Verifying Precisely

For events with many fields, use a captor to verify `eventId`, `aggregateId`, `occurredAt`, and `schemaVersion` according to the rules. If timestamps come from `Instant.now()`, avoid brittle "approximate time" assertions; inject a fixed `Clock` or compare within a controlled range.

For example:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-01-01T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

This is an illustrative Java snippet requiring imports for `Clock`, `Instant`, and `ZoneOffset`. Injecting a clock into the service gives event timestamps deterministic values in tests.

### 14.5. Exactly One Event or Exactly One Invocation?

`verify(publisher).publishEvent(...)` checks **code invocation**, not that Spring delivers to exactly one listener. One event can have multiple listeners, a listener can be invoked again, or an event can be retried by an external broker. Do not treat publisher invocation count as a substitute for exactly-once processing.

## 15. Choosing the Right Test Double

| Tool | Most Useful When | What It Cannot Prove |
| --- | --- | --- |
| `Mockito.mock(ApplicationEventPublisher.class)` | Verifying publish, payload, count, and ordering | Listener dispatch, commit, async, durability |
| Fake `ApplicationEventPublisher` storing a list | Collecting events for readable content assertions | Spring annotations/proxies/dispatch |
| Mocking listener dependencies | Testing event-handling logic in isolation | Listener is genuinely registered |
| `@RecordApplicationEvents` | Recording events in Spring integration tests | Every listener finished, durability |
| Capturing listener/spy with real context | Proving a listener truly receives/handles events | Commit policy without a transaction test |
| Testing with a real transaction manager | Commit/rollback, after-commit | Durable delivery across process crashes |
| Testing real or fault-injected outbox/broker | Retries, idempotency, recovery | Does not replace publisher semantic tests |

**Recommendation by complexity:** start with producer unit tests using Mockito; add a small integration test proving event wiring; add transaction/async/replay tests if the feature requires them. Avoid using a heavy `@SpringBootTest` for every assertion that only needs a mock.

## 16. Common Mistakes

1. **Mocking the publisher and concluding listeners ran:** a mock only records invocations, not dispatch.
2. **Reading `verify(publisher)` as proof the database committed:** the transaction can roll back after publish.
3. **Emitting an event for an unsuccessful command:** `OrderPlaced` must not be emitted when validation fails.
4. **Not checking payload fields:** the test knows an event exists but misses wrong order IDs or amounts.
5. **Not testing error branches:** the service emits an event even though the repository throws an exception.
6. **Confusing `publishEvent(ApplicationEvent)` and `publishEvent(Object)` overloads:** Mockito verifies the wrong method signature.
7. **Using mutable events without `equals` and verifying with a new instance:** easily fails or hides bugs; use records/captors.
8. **Using `verifyNoInteractions` on a mock shared across multiple initialization paths:** assertions become sensitive to unrelated setup.
9. **Verifying every internal call detail:** tests become brittle on refactoring even while the contract stays intact.
10. **Using `@SpringBootTest` just to check that a method calls the publisher:** wastes time without adding value.
11. **Replacing the real publisher in integration tests with a mock:** prevents the event bus from dispatching as in production.
12. **Assuming `ApplicationEvents` recording an event means async workers finished:** you must await the real outcome.
13. **Letting a test finish in an auto-rolled-back transaction while expecting `AFTER_COMMIT` to run:** manage transaction boundaries explicitly.
14. **Treating `@RecordApplicationEvents` as an event store:** it only records events within test scope.
15. **Not separating immediate repository errors from commit failures:** mocking a save exception does not simulate all rollback paths.
16. **Using `Thread.sleep` for async integration tests:** flaky, dependent on scheduler and CI load.
17. **Not testing duplicate event emissions:** consumers may receive unwanted multiple events even for a single API call.
18. **Using Mockito mocks as proof of reliable delivery:** only outbox/broker/recovery tests verify durability.
19. **Mocking the domain event itself:** the test fails to verify a real business fact.
20. **Renaming events/schemas without updating integration contracts:** downstream consumers may still rely on old types/versions.

## 17. Practice Exercises

1. In a `placeOrder` use case, why can a unit test use `mock(ApplicationEventPublisher.class)` without opening a Spring context?
2. What does `verify(publisher).publishEvent(...)` prove? What does it not prove?
3. When should you use `ArgumentCaptor<Object>` instead of `verify` with a new event object?
4. Distinguish the `publishEvent(Object)` and `publishEvent(ApplicationEvent)` overloads in Java.
5. Why is the `OrderPlaced` record convenient for `equals`-based assertions?
6. If `repository.save` throws `RuntimeException` immediately, should the test expect the publisher to be called?
7. If `repository.save` returns normally but the transaction commit fails later, can a unit test using a mocked publisher detect it?
8. Why is `InOrder` useful when save/publish order is part of the contract, and why does it not prove after-commit?
9. When an integration test wants to confirm an `@EventListener` actually receives the event, should you keep the real publisher or mock it?
10. What kind of observation does `@RecordApplicationEvents` provide? Does it replace asserting listener outcomes?
11. With an `@Async` listener, why is confirming publish insufficient to assert an email was sent?
12. If an event is redelivered after a process crash, does a Mockito publisher unit test verify consumer idempotency?
13. Why is a fake publisher storing a list of events sometimes easier to read than a mock with many matchers?
14. When an event contains `Instant.now()`, what technique makes the test deterministic and non-flaky?

**Answer guide:** (1) the interface is injected and mocked, pure JVM test; (2) invocation happened, not dispatch/commit/delivery; (3) when you want to inspect the exact runtime type/fields or `equals` is unsuitable; (4) overload is chosen by the compiler from the argument's static Java type; (5) records have component-based `equals`; (6) no; (7) no; (8) verifies call order before/after but not DB commit; (9) real publisher; (10) records published events in test, still need separate listener outcome checks; (11) worker runs later and may fail; (12) no; (13) fewer library dependencies, list is easy to assert; (14) inject `Clock.fixed`.

## 18. Summary

**Mocking `ApplicationEventPublisher`** is a fast and accurate technique for unit testing domain event **producers**:

- Inject the narrow interface via constructor.
- Use Mockito to mock the publisher and repository.
- Use `verify`, `ArgumentCaptor`, and `InOrder` to verify event type, payload, count, and ordering.
- Test invalid input/repository error branches to assert no success event is emitted.
- Watch out for the `publishEvent(Object)` and `publishEvent(ApplicationEvent)` overloads.
- Do not confuse verifying an invocation with dispatch, commit, after-commit, async completion, or durable delivery.
- When needing to confirm Spring event wiring, use a real publisher with `@RecordApplicationEvents`/`ApplicationEvents` and a listener with observable outcomes.
- When needing to test transactions, async, or outboxes, add integration tests at the proper boundary rather than forcing a publisher mock to prove behavior it does not execute.

## References

- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Application Events in TestContext*: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework 6.2.8 Javadoc — *RecordApplicationEvents*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEvents*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework Reference — *Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Mockito official API — *Mockito*: https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org/mockito/Mockito.html
- Mockito official API — *ArgumentCaptor*: https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org/mockito/ArgumentCaptor.html
