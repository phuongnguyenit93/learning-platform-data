# Testing That a Publisher Emits the Right Event in Spring Framework

## 1. Goal of the Test

In Spring Framework, `ApplicationEventPublisher` enables a component to publish events without directly calling every consumer:

```java
publisher.publishEvent(new OrderPlaced(orderId, quantity));
```

What matters in testing is not merely verifying that the line `publishEvent(...)` ran once. A quality test must answer **whether the publisher emits the right event according to the business contract**:

1. **Right event type:** `OrderPlaced`, not `OrderCancelled` or an overly generic type.
2. **Right payload:** `orderId`, quantity, version, `eventId`, and meaningful values are mapped accurately.
3. **Right emission count:** exactly once for a successful action; no accidental duplicate emission.
4. **Right condition:** invalid data or an operation that fails before the publish point must not publish a success event.
5. **Right timing/context:** know whether the event is emitted immediately when the command runs or only upon successful commit.
6. **Right test boundary:** a mock publisher verifies only the **Java invocation**; Spring Test records events to verify **the actual event published in the `ApplicationContext`**.

This article belongs to the **Event Testing** group under **Spring Framework Application Events**. The primary example uses Java 17+, Spring Framework 6.2.12, JUnit Jupiter, and Mockito, without requiring Spring Boot, an HTTP server, or a database.

## 2. What Does `publishEvent(...)` Actually Confirm?

`ApplicationEventPublisher` has an API with two important overloads:

```java
void publishEvent(ApplicationEvent event);
void publishEvent(Object event);
```

These are **illustrative API signatures**, located in `org.springframework.context.ApplicationEventPublisher`. An event can be a class extending `ApplicationEvent` or a plain Java object/record.

For example:

```java
public record OrderPlaced(String orderId, int quantity) {}

publisher.publishEvent(new OrderPlaced("O-101", 3));
```

With a record that does not extend `ApplicationEvent`, the `publishEvent(Object)` overload is used. When Spring dispatches an object-typed event, the infrastructure may wrap it in a `PayloadApplicationEvent`, yet an `@EventListener` consumer declaring an `OrderPlaced` parameter can still receive the **`OrderPlaced` payload**, and Spring Test's `ApplicationEvents.stream(OrderPlaced.class)` can filter those exact payloads.

Understand the limitations:

- `publishEvent(...)` returns **`void`**. It returns neither a result nor the count of successful listeners.
- With the default synchronous multicaster, listeners are typically processed on the publisher thread.
- When configuring an asynchronous multicaster, `@Async`, or transaction-phase listeners, `publishEvent()` can return **before post-processing finishes**.
- A test verifying that the publisher invoked the right event **does not prove** that an email, DB write, or HTTP request inside a listener succeeded.
- If a synchronous listener throws an exception and no error handler swallows it, the exception can propagate back to the publisher. Therefore, clearly separate publisher tests, listener tests, and full-flow tests.

**The contract to test** should be written as a single sentence: "When submitting a valid order with a given ID and quantity, the publisher emits **exactly one** `OrderPlaced` with accurate data; when data is invalid, no `OrderPlaced` is emitted."

## 3. Two Complementary Testing Levels

| Approach | What It Verifies | What It Does Not Automatically Prove |
| --- | --- | --- |
| **Unit test** mocking `ApplicationEventPublisher` with Mockito | The service called the publisher with the right event type, payload, count, and condition | Spring event infrastructure, component scan, listener registration, transaction phase |
| **Integration test** with `@RecordApplicationEvents` and `ApplicationEvents` | The event was actually published in the Spring `ApplicationContext` within the test method scope | Async listener completion, external side-effect success, event durability across crashes |
| **Listener/flow integration test** | The handler was invoked and the final state was produced per a specific contract | Every production infrastructure failure, especially external brokers/DBs outside the test |
| **End-to-end test** | The entire workflow from API to DB/broker/consumer | Does not replace small, fast unit tests that pinpoint failure causes |

**Do not treat them as mutually exclusive:** unit tests catch data-mapping bugs in the service very quickly; integration tests ensure the Spring publish path works as expected.

A common mistake is writing:

```java
verify(publisher).publishEvent(any());
```

Without checking the overload, event type, and payload, the test only proves **a vague invocation** occurred. For instance, a service emitting `OrderCancelled` instead of `OrderPlaced` could still pass an overly loose test. Use `ArgumentCaptor` or match against a concrete object/value object.

## 4. Complete Java 17+ Example: Unit Test and Integration Test for the Same Publisher

This project is intentionally small so it runs on any machine with JDK 17+ and Gradle 8+.

It contains one service:

- `submit("O-41", 3)` emits `OrderPlaced("O-41", 3)` and returns the ID.
- A blank ID or non-positive quantity causes the method to throw `IllegalArgumentException` **before** calling the publisher.
- No repository/database: this exercise measures publish behavior precisely, avoiding mixing in DB rollback when not yet needed.

Two test classes verify **five test cases**:

- 2 unit tests using Mockito;
- 3 integration tests using Spring Test `@RecordApplicationEvents`.

### 4.1. Directory Structure

```text
publisher-event-tests/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/OrderWorkflow.java
    └── test/java/demo/
        ├── OrderPublisherUnitTest.java
        └── OrderEventsIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'publisher-event-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testImplementation 'org.mockito:mockito-core:5.15.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Versions:** These dependency coordinates illustrate a compatible Spring Framework 6.2.x and Java 17 set. In real projects, use dependency management/BOM to keep Spring/JUnit versions consistent. `spring-test` is in `testImplementation` because it is only used in tests; Mockito likewise does not appear in production sources.

This is a plain Java project without the Spring Boot plugin. `gradle test` builds the main and test classpaths and runs JUnit Jupiter via the JUnit Platform.

### 4.2. `src/main/java/demo/OrderWorkflow.java`

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class OrderWorkflow {

    private OrderWorkflow() {
    }

    // Event is an immutable value object.
    public record OrderPlaced(String orderId, int quantity) {}

    // Another event to verify the wrong type is not emitted.
    public record OrderCancelled(String orderId) {}

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public String submit(String orderId, int quantity) {
            if (orderId == null || orderId.isBlank()
                    || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            publisher.publishEvent(
                    new OrderPlaced(orderId, quantity));
            return orderId;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }
}
```

Explanation:

- `OrderPlaced` is a Java record. Records are compared by **value** (`equals`) of their components, which is very convenient for assertions.
- The service receives `ApplicationEventPublisher` via its constructor, so it **can be unit tested with a mock** without starting a Spring context.
- `submit(...)` validates **before publishing**. The invalid-input test must prove no success event is emitted.
- `OrderCancelled` serves only as an event-type control; this service **never** publishes `OrderCancelled`.
- `@Configuration` provides the service bean for the integration test. There is no `@ComponentScan`, so it does not depend on package structure beyond the three files in the project.
- The publisher is provided by the Spring context as a dependency; you do not define a publisher bean manually.

In real applications, IDs and event details typically come from an aggregate or persistence result. Events should be immutable DTOs/snapshots, avoiding passing mutable entities or request-bound objects directly.

### 4.3. Unit Test — `src/test/java/demo/OrderPublisherUnitTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class OrderPublisherUnitTest {

    @Test
    void publishesOneCorrectOrderPlacedEvent() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);

        OrderWorkflow.OrderService service =
                new OrderWorkflow.OrderService(publisher);

        String result = service.submit("O-41", 3);

        ArgumentCaptor<OrderWorkflow.OrderPlaced> captor =
                ArgumentCaptor.forClass(
                        OrderWorkflow.OrderPlaced.class);

        verify(publisher, times(1))
                .publishEvent(captor.capture());

        OrderWorkflow.OrderPlaced event =
                captor.getValue();

        assertEquals("O-41", result);
        assertEquals(
                new OrderWorkflow.OrderPlaced("O-41", 3),
                event);
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidInputDoesNotCallPublisher() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);

        OrderWorkflow.OrderService service =
                new OrderWorkflow.OrderService(publisher);

        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.submit("O-42", 0));

        assertEquals("invalid order", ex.getMessage());
        verifyNoInteractions(publisher);
    }
}
```

**Why is this a stronger unit test than `verify(publisher).publishEvent(any())`?**

- `ArgumentCaptor<OrderPlaced>` enforces receiving the exact event type when the test inspects the call.
- `assertEquals(new OrderPlaced("O-41", 3), event)` verifies both **type** and **every field's value**, thanks to `record.equals`.
- `times(1)` verifies **that the same call is not emitted more than once**.
- `verifyNoMoreInteractions(publisher)` verifies no additional publisher calls occurred beyond the verified invocation.
- The invalid-input test uses `verifyNoInteractions(...)` to prove **the publisher was not called at all**.
- The service is instantiated via `new`, with no Spring container: the test focuses purely on **publisher invocation logic**.

**Note on overloads:** `OrderPlaced` is a record that does not extend `ApplicationEvent`, so `publishEvent(captor.capture())` verifies the `publishEvent(Object)` overload of the API. If replaced with an `ApplicationEvent` subclass, Mockito verification must match the overload and actual argument type; avoid accidentally matching an uncalled overload.

## 5. Integration Testing with `@RecordApplicationEvents`

Spring TestContext Framework provides:

- `@RecordApplicationEvents` (package `org.springframework.test.context.event`): requests recording of application events published within the scope of a test.
- `ApplicationEvents`: API for retrieving recorded events as a `Stream`.
- `ApplicationEventsTestExecutionListener`: sets up and maintains the recorder in TestContext; **registered by default** unless you replace the entire `TestExecutionListener` list.
- `@SpringJUnitConfig`: combines `SpringExtension` and context configuration for JUnit Jupiter.

For example:

```java
events.stream(OrderWorkflow.OrderPlaced.class).toList();
```

This retrieves **events or payloads** of type `OrderPlaced`. With `publisher.publishEvent(new OrderPlaced(...))`, Spring may wrap the object in `PayloadApplicationEvent` for dispatch, yet `ApplicationEvents.stream(OrderPlaced.class)` remains the right API for testing event payloads by type.

### 5.1. `src/test/java/demo/OrderEventsIntegrationTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(OrderWorkflow.Config.class)
@RecordApplicationEvents
class OrderEventsIntegrationTest {

    @Autowired
    OrderWorkflow.OrderService service;

    @Test
    void successfulSubmitPublishesExactEvent(
            ApplicationEvents events) {

        String id = service.submit("O-41", 3);

        List<OrderWorkflow.OrderPlaced> published =
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .toList();

        assertEquals("O-41", id);
        assertEquals(1, published.size());
        assertEquals(
                new OrderWorkflow.OrderPlaced("O-41", 3),
                published.get(0));

        // Do not accidentally emit another business event type.
        assertEquals(0,
                events.stream(OrderWorkflow.OrderCancelled.class)
                        .count());
    }

    @Test
    void invalidSubmitPublishesNoSuccessEvent(
            ApplicationEvents events) {

        assertThrows(
                IllegalArgumentException.class,
                () -> service.submit("O-42", 0));

        assertEquals(0,
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .count());
    }

    @Test
    void twoValidSubmitsPublishTwoCorrectPayloads(
            ApplicationEvents events) {

        service.submit("O-1", 1);
        service.submit("O-2", 2);

        List<OrderWorkflow.OrderPlaced> expected = List.of(
                new OrderWorkflow.OrderPlaced("O-1", 1),
                new OrderWorkflow.OrderPlaced("O-2", 2));

        List<OrderWorkflow.OrderPlaced> actual =
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .toList();

        assertEquals(2, actual.size());
        assertIterableEquals(expected, actual);
    }
}
```

**Explanation of each test:**

- `successfulSubmitPublishesExactEvent`: the service is a real Spring bean and the publisher is the context's implementation. `ApplicationEvents` verifies the event was published. It checks the exact type, `orderId`, quantity, emission count, and absence of `OrderCancelled`.
- `invalidSubmitPublishesNoSuccessEvent`: tests the failure path. Correct behavior is not always "an event exists," but rather **not publishing a success event when validation fails**.
- `twoValidSubmitsPublishTwoCorrectPayloads`: checks two independent actions and two corresponding payloads. With the default synchronous publisher and multicaster in this example, the two events are recorded in the order `submit` is called on the test thread.

`ApplicationEvents events` is supplied by `SpringExtension` via a **test method parameter**. This approach is recommended by Spring documentation because the recorder is scoped **per test method**. Do not inject `ApplicationEvents` into the test class constructor; it is not intended for use outside a test method's lifecycle.

If you prefer using a field:

```java
@Autowired
ApplicationEvents events;
```

This is an illustrative alternative to a method parameter. Spring documentation permits this approach, though it still requires accessing it while a test method is active. Do not store `ApplicationEvents` in a singleton application bean or in a static field for reuse across multiple tests.

### 5.2. Running All Five Test Cases

In the project directory containing `build.gradle`, run:

```bash
gradle clean test
```

If using the Gradle Wrapper, run `./gradlew clean test` on Linux/macOS or `gradlew.bat clean test` on Windows. The sample project does not include a wrapper.

**Expected outcome:** Gradle/JUnit Jupiter runs **5 test methods**, with zero assertion failures, and the `test` task succeeds. Gradle's success line may read `BUILD SUCCESSFUL`, while timing, up-to-date status, test order, and console formatting depend on the environment; **there is no single fixed stdout string required to consider the tests passing**.

You can view the HTML report at:

```text
build/reports/tests/test/index.html
```

This report is generated by Gradle, not a file the example asks you to author manually. If a test fails to load the context or record events, inspect annotations/packages, resources, and the `TestExecutionListener` list before concluding the publisher is faulty.

## 6. Aspects to Verify in an Event Contract

The test code above does not include a timestamp or event ID. In real-world projects, payloads are usually richer:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        long aggregateVersion,
        String customerId,
        int quantity,
        Instant occurredAt) {}
```

This is a separate **illustrative** definition and does not replace the `OrderPlaced` record in the runnable project in section 4. It requires importing `java.time.Instant`.

Do not write only:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

Counting is certainly useful, but if the publisher emits one event with **the wrong customer or quantity**, that test still passes. Verify all important fields:

```java
OrderPlaced event = events.stream(OrderPlaced.class)
        .findFirst()
        .orElseThrow();

assertEquals("O-41", event.orderId());
assertEquals("C-9", event.customerId());
assertEquals(3, event.quantity());
assertEquals(7L, event.aggregateVersion());
```

The snippet above is **illustrative**, assuming `OrderPlaced` is the extended record and the event has already been recorded. For randomly generated/UUID `eventId` and `occurredAt` from a clock, inject a `Clock` or validate properties instead of comparing timestamps against `Instant.now()` at a different instant.

Test structure should reflect the contract:

| Condition | Verification |
| --- | --- |
| Valid submit | Exactly one `OrderPlaced` |
| Invalid submit | No success `OrderPlaced` |
| Processing two distinct submits | Two events with distinct IDs/payloads |
| Rejected action | No success event emitted; failure event only if required by contract |
| State transition from A to B | Event contains accurate old/new state and version |
| Event contains a collection | Payload is an immutable snapshot; unchanged if the source entity is mutated later |
| Duplicate publish with same ID | Assert `times(1)` or design idempotency and test duplicate semantics |
| Same-type events from elsewhere | Filter by `orderId`/eventId; do not pick an arbitrary same-type event to draw conclusions |

Separating **input conditions**, **event type**, **payload**, and **emission count** into explicit assertions produces much more useful failure messages than one vague assertion.

## 7. Recording a Published Event Does Not Prove Listeners Finished Processing

Distinguish three milestones:

```text
Publisher creates Event
    |
    +-- publishEvent(Event)
          |
          +-- ApplicationEvents recorder: event has been published
          |
          +-- Synchronous listener: processed immediately by default multicaster
          |
          +-- @Async listener: may only have been submitted to an executor
          |
          +-- @TransactionalEventListener(AFTER_COMMIT):
                 may only be registered awaiting commit
```

Therefore:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

**Is not equivalent** to:

```text
email sent successfully
payment captured
audit row committed
listener completed
```

In Spring Test, `@RecordApplicationEvents` is meant for recording **events published within the context**. To test a listener, write a dedicated test using state, a spy, a DB, or an observer that confirms execution.

For async listeners, use `CountDownLatch`, `CompletableFuture`, Awaitility, or a status signal with a timeout. Never use `Thread.sleep(100)` hoping the worker finishes. If the service requires guaranteed delivery across process restarts, in-memory Spring Application Events do not replace an event store, outbox, or message broker.

### When `@Async` Is Present

The `ApplicationEvents` recorder is scoped to the test thread and threads aligned with the test context; **do not assume it captures every event emitted from arbitrary thread pools**, especially pre-created thread pools that do not carry the corresponding `TestContext`. The reliable approach is testing the publisher directly with a mock in a unit test and testing the async consumer path via a test-managed observer/latch mechanism.

If you need to assert an event chain A → B emitted on a worker, an observer registered in the context can proactively capture B and signal a latch. Never infer "A was published" means B must already be present when the assertion runs.

## 8. Transactions: A Published Event Does Not Mean the Transaction Committed

Example:

```java
@Transactional
public void createOrder(OrderCommand command) {
    repository.save(toEntity(command));
    publisher.publishEvent(new OrderPlaced(command.id(), 2));
    // An exception thrown below here can roll back the transaction.
}
```

This is an illustrative snippet; `repository`, `OrderCommand`, and `toEntity(...)` belong to application code, not the runnable project.

A `@RecordApplicationEvents` test can record `OrderPlaced` **as soon as the publisher is called**, even if the transaction subsequently rolls back. Therefore distinguish:

- **Testing the publisher:** verify the service emits the right event at call time.
- **Testing transaction outcome:** verify the DB commits or rolls back according to the contract.
- **Testing post-commit listeners:** verify `@TransactionalEventListener(AFTER_COMMIT)` processes the event only when the transaction commits successfully.

Illustrative event listener structure:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Runs only after successful commit of the transaction
    // that registered the event, not immediately at publishEvent().
}
```

With `@TransactionalEventListener`, if no matching transaction is active when the event is emitted, the listener does not run by default (`fallbackExecution=false`). Do not treat "the listener did not run" as proof that the service failed to emit the event; the event may **have been published without an active transaction to register the callback**.

### Pitfall of `@Transactional` Tests

Spring Test typically rolls back a test method's transaction by default. If a test is annotated with `@Transactional`, calls a service, and immediately checks an `AFTER_COMMIT` listener before the transaction ends, the callback **has not run yet**. At the end of the test, the test transaction may roll back, so the listener is never invoked.

When you need to test an actual commit, use `TestTransaction` to explicitly complete it:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Now verify the DB or post-commit listener.
```

This is an illustrative snippet requiring the test to be inside a Spring Test-managed transaction and importing `org.springframework.test.context.transaction.TestTransaction`. It is omitted from the main example because the main project intentionally has no database. Another option is leaving the test method **non-transactional** and calling a transactional service; the service proxy commits before assertions check DB state.

Important note when a transaction rolls back: if an event was published **before rollback**, `ApplicationEvents` assertions can still see it. A proper test must be explicit about whether it checks *publish* or *commit-bound consumption*.

## 9. Distinguishing Spring Test `ApplicationEvents` from Related Components

Similar names can cause confusion:

- `ApplicationEventPublisher`: **production** interface used to publish events.
- `ApplicationEvents` in `org.springframework.test.context.event`: **Spring Test** API for accessing events recorded during a test.
- `ApplicationListener<T>`: **production** handler by event type.
- `@EventListener`: annotation-based method handler.
- `@TransactionalEventListener`: handler bound to a transaction phase.
- `PayloadApplicationEvent<T>`: wrapper for object-payload events.
- `ApplicationEventMulticaster`: dispatch infrastructure to listeners.

`@RecordApplicationEvents` neither creates events nor replaces `ApplicationEventPublisher`. It only helps **observe emitted events**, avoiding writing a manual test listener in simple cases.

You can call `ApplicationEvents.clear()` to clear events recorded in **the current test method** if you want to start a fresh observation window. However, do not call `clear()` indiscriminately in a way that hides unexpected prior events. In the example, each test method has its own managed recorder, so `clear()` is unnecessary.

### What Happens with Custom `@TestExecutionListeners`?

`ApplicationEventsTestExecutionListener` is part of Spring Test's default listener set. If a test class declares:

```java
@TestExecutionListeners(
        listeners = CustomListener.class,
        mergeMode = TestExecutionListeners.MergeMode
                .MERGE_WITH_DEFAULTS)
```

This is an **illustrative snippet**; `CustomListener` is a project-defined test utility class not present in the runnable example. Using `MERGE_WITH_DEFAULTS` preserves the default listeners, including the one supporting Application Events recording. If you **replace the entire** default list and forget to include `ApplicationEventsTestExecutionListener`, `@RecordApplicationEvents` may not work as expected.

You do not need to declare `ApplicationEventsTestExecutionListener` manually when using the default TestContext as in the example.

## 10. Common Mistakes When Writing Publisher Tests

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Writing only `verify(publisher).publishEvent(any())` | Does not check event type or payload; may match the wrong overload | Use a typed `ArgumentCaptor` or value-object equality |
| Asserting only `count() == 1` | Event may carry wrong important fields | Verify `orderId`, quantity, version, eventId |
| Asserting only that the event appeared at least once | Misses duplicate publishing | Assert exact count and no-more-interactions in unit tests |
| Assuming the event type is an `ApplicationEvent` subclass | Object payloads are often wrapped by Spring in `PayloadApplicationEvent` | Use `events.stream(MyPayload.class)` to filter payloads |
| Asserting an event appeared before triggering the action | Setup/previous events are counted in the result | Filter by exact event type/id; note per-method recorder scope |
| Using a mock publisher and claiming Spring dispatched it | Mockito only sees method calls on the mock | Add an integration test with `@RecordApplicationEvents` |
| Reading `ApplicationEvents` in the test constructor | Recorder is method-scoped and not ready in the constructor | Inject into `@Test` method or an `@Autowired` field |
| Losing the recorder when customizing `TestExecutionListeners` | Dropped the default listeners | Use `MERGE_WITH_DEFAULTS` or declare the listener explicitly |
| Testing transaction rollback while expecting `AFTER_COMMIT` | Callback runs only after successful commit | Explicitly commit/end the test transaction per contract |
| Event published before rollback still appears in recorder | Recorder measures publish, not commit | Separate publish assertions from post-commit assertions |
| Async test using `Thread.sleep` | Results flake with scheduler timing | Use latch/future/await with a timeout |
| Listener handles same-type events multiple times | Chaining/republication or multiple publishers of same type | Filter by eventId; inspect publish paths and counts |

## 11. Designing Stable Tests in Large Applications

### 11.1. Producing Events from Deterministic Data

If an event has `occurredAt`, inject a `Clock` instead of calling `Instant.now()` directly:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC);
```

This is illustrative code requiring imports for `java.time.Clock`, `java.time.Instant`, and `java.time.ZoneOffset`. When a service uses a fixed clock, timestamps can be asserted deterministically. For random UUIDs, inject a `Supplier<UUID>`/factory so tests use fixed IDs, or assert only uniqueness and correlation according to the contract.

### 11.2. Do Not Pass Mutable Events into Async Tests

If an event holds an entity or request object, a `@RecordApplicationEvents` test seeing the right payload at publish time **does not prove** that object remains unchanged when an async listener reads it. For payloads requiring snapshots, test:

```text
create immutable event snapshot
publish event
mutate source entity
assert snapshot still retains initial values
```

Make defensive copies for nested collections and mutable elements, rather than merely wrapping the outer shell in a Java record. This keeps the event contract resilient when changing multicasters or adding async listeners.

### 11.3. Parent/Child Contexts

Spring Application Events from a child context can propagate up to the parent. A recorder/listener in the parent can observe events emitted by the child, unexpectedly inflating counts. In multi-context applications, tests should identify the **source context** and filter only events within the scope being verified.

Do not assume "there is exactly one event in the entire application" when Boot/MVC apps have multiple contexts, libraries emit startup events, or other listeners republish events. Filter by **event type + business/correlation ID**.

### 11.4. Independent Scope per Test

Although Spring Test typically caches the `ApplicationContext` across test methods, the `ApplicationEvents` recorder is scoped per test method. Therefore, never store `ApplicationEvents` in a singleton bean or static field; use a method parameter for simplicity.

In Mockito unit tests, create a fresh mock publisher per test as shown in the example. If using `@BeforeEach` with a shared mock, call `reset(...)` only for a clear reason; avoid cross-test contamination. For async events, clean up executors/futures via the test framework so leftover tasks do not affect subsequent tests.

### 11.5. Watch What Is Out of Scope for Publisher Unit Tests

A unit test mocking the publisher does not verify:

- `@EventListener` is registered by Spring for the right type;
- `@Order` listeners execute in the expected order;
- `@Async` proxies actually invoke an executor;
- transaction commit/rollback actually happens;
- DB inserts/HTTP/email/broker operations complete;
- events are persisted/replayed across restarts.

Those requirements belong to integration tests or end-to-end tests. Keep unit tests small so they fail for only one reason: the service failed to emit an event matching its contract.

## 12. Application Checklist

Before finishing an event publisher test suite, verify:

- **Trigger:** did the test actually invoke the business action expected to emit the event?
- **Type:** did you verify the exact concrete event class/record?
- **Count:** did you check the exact emission count and ensure no duplicates?
- **Payload:** did you assert all important fields rather than merely event existence?
- **Negative path:** does invalid input or failure before publish avoid emitting a success event?
- **Overload:** is Mockito verifying the right `publishEvent(Object)` or `publishEvent(ApplicationEvent)` overload?
- **Spring integration:** is there a test with a real context or `@RecordApplicationEvents` when dispatch paths need verification?
- **Async:** are you using a deterministic wait mechanism when testing async listeners?
- **Transaction:** have you separated "published" from "committed" and post-commit effects?
- **Isolation:** does each test method have its own recorder/mock without interference from other context events?
- **Event contract:** is the payload immutable, holding no request-, thread-, or persistence-context-bound objects?

**Conclusion:** To test that a publisher emits the right event, use **Mockito's typed `ArgumentCaptor`** in unit tests to verify event type, payload, emission count, and error paths; use **`@RecordApplicationEvents` + `ApplicationEvents.stream(EventType.class)`** in Spring Test to verify the event is actually published in the `ApplicationContext`. Clearly separate **publishing** from listener completion or transaction commit; doing so keeps tests both accurate and far less flaky.

## Official References

- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — `ApplicationEvents` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito — ArgumentCaptor](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/ArgumentCaptor.html)
