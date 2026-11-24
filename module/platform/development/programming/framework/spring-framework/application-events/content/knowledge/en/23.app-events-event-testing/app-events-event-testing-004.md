# @RecordApplicationEvents: Testing Spring Application Events

`@RecordApplicationEvents` is a **Spring Framework TestContext** annotation used to record application events published in the `ApplicationContext` during the lifecycle of **a single test method**. Afterward, the test reads the recorded events via the `ApplicationEvents` API to confirm which events an action actually emitted, how many times, and what their payloads contained.

Use-case example: when calling `OrderService.placeOrder("PO-42")`, the service must publish exactly one `OrderPlaced` with order ID `PO-42`. Instead of creating a mock `ApplicationEventPublisher` and merely verifying `publishEvent(...)` was called, an integration test can let a **real Spring Context** publish the event and use `@RecordApplicationEvents` to collect the outcome.

**Package note:** This is **not a Spring Boot-specific annotation**. It has been available since Spring Framework **5.3.3** in `org.springframework.test.context.event.RecordApplicationEvents` inside the `spring-test` artifact. Spring Boot can use this annotation because `@SpringBootTest` integrates Spring TestContext, and a plain Spring test with `@SpringJUnitConfig` can use it as well.

## 1. What Problem Does @RecordApplicationEvents Solve?

When testing event-driven code, we want to separate three questions:

1. **Did the publisher emit the right event?** Inspect `ApplicationEvents.stream(OrderPlaced.class)`.
2. **Did the listener perform the right side effect?** Inspect the state produced by the listener separately, such as a repository, a fake notification gateway, or a spy.
3. **Did the business transaction commit successfully?** Inspect the transaction/database outcome; **counting published events does not prove commit**.

`@RecordApplicationEvents` directly answers **the first question**. It is not a message broker, does not generate events itself, does not guarantee listeners finished, and does not replace assertions on the database or external services.

```text
Test method (Spring TestContext)
    |
    +-- @RecordApplicationEvents
    |        |
    |        +-- ApplicationEventsTestExecutionListener prepares the recorder
    |        +-- ApplicationEvents is available for the test method lifecycle
    |
    +-- call OrderService.placeOrder(...)
                |
                +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                            |
                            +-- event multicaster invokes matching listeners
                            |
                            +-- recorder retains published events
    |
    +-- events.stream(OrderPlaced.class)
    |        +-- verify count, payload, order ID, sequence...
    |
    +-- end of test method -> recorder for that method ends
```

You do not need to declare a production `ApplicationEvents` bean. Spring TestContext supplies a **test-scoped resolvable dependency** when the annotation and `ApplicationEventsTestExecutionListener` are active.

## 2. Related Components

| Component | Package / Role | Key Points |
| --- | --- | --- |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Placed on a **test class** or used as a meta-annotation; do not use it as an annotation on a single test method |
| `ApplicationEvents` | `org.springframework.test.context.event` | Accesses events recorded during the current test lifecycle |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Enables recording; registered **by default** by Spring TestContext |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Combines `SpringExtension` and Spring test context config for JUnit 5 |
| `@SpringBootTest` | `org.springframework.boot.test.context` | Can replace `@SpringJUnitConfig` when a Boot application context is needed |
| `ApplicationEventPublisher` | `org.springframework.context` | Production API for publishing events |
| `@EventListener` | `org.springframework.context.event` | Defines event-handling methods, independent of the test recorder |

`@RecordApplicationEvents` works only when the test runs within the **Spring TestContext framework**, for example via `SpringExtension` with JUnit Jupiter. Running a plain JUnit test without loading a Spring context and simply adding this annotation will not create a recorder automatically.

### Per-Test-Method Lifecycle

`ApplicationEvents` is bound to **the current test method's lifecycle**, not a singleton holding event history across an entire test suite. If a test class has multiple `@Test` methods, each test gets its own recorded events for that run.

You can obtain `ApplicationEvents` in two common ways:

**Recommended with JUnit 5:** as a parameter to `@Test`, `@BeforeEach`, or `@AfterEach`:

```java
@Test
void publishOrder(ApplicationEvents events) {
    // events belongs to this test method.
}
```

**Field approach:**

```java
@Autowired
ApplicationEvents events;
```

Both snippets are **skeleton code** and must live inside a test class annotated with `@RecordApplicationEvents` and an appropriate Spring context.

Do not inject `ApplicationEvents` via the **test class constructor**: at constructor execution time, the test-method lifecycle is not yet ready. Spring TestContext documentation explicitly states to use this instance only within a test method lifecycle. Do not pass `ApplicationEvents` into a production singleton bean to hold it as a long-lived dependency.

## 3. The ApplicationEvents API

The core API has three methods:

```java
Stream<ApplicationEvent> stream();
<T> Stream<T> stream(Class<T> type);
void clear();
```

These are **abbreviated signatures** of the `ApplicationEvents` interface, not a standalone Java program.

### 3.1. stream(Class<T>): Filtering by Event/Payload Type

```java
long count = events.stream(OrderPlaced.class).count();

List<OrderPlaced> orderEvents =
        events.stream(OrderPlaced.class).toList();
```

If `OrderPlaced` is a record/POJO published via `publishEvent(new OrderPlaced(...))`, Spring may wrap it in `PayloadApplicationEvent`. `stream(OrderPlaced.class)` still returns **payloads of type `OrderPlaced`**, letting you assert contents without casting the wrapper.

Filtering by type is especially important because the context can publish many other framework events: refresh, lifecycle, test events, or events from other components. Do not assert total `events.stream().count() == 1` just because your service publishes one event.

### 3.2. stream(): Viewing All ApplicationEvents

```java
events.stream().forEach(event ->
        System.out.println(event.getClass().getSimpleName()));
```

This returns a stream of the actual recorded `ApplicationEvent` instances, which may include `PayloadApplicationEvent<?>` when the publisher emits POJOs. Use it to inspect, categorize, or debug events; normally business tests should prefer `stream(MyDomainEvent.class)` to reduce noise.

### 3.3. clear(): Clearing Events Recorded in the **Current Method**

```java
events.clear();

service.placeOrder("PO-43");

assertEquals(1L, events.stream(OrderPlaced.class).count());
```

`clear()` clears **the event list held by the recorder**; it does not roll back transactions, clear the database, re-invoke listeners, alter publisher state, or wait for async events to finish. Therefore, `clear()` can establish a clean observation boundary between two actions within the same test.

## 4. Complete Java 17+ Example: Spring Test + JUnit 5 + @RecordApplicationEvents

This example uses **Spring Framework 6.2.9**, with no Spring Boot or database needed. We create a Spring-managed service that emits an `OrderPlaced` record, verify the first emission, clear the recorder, and verify the second emission. There is only **one test method**, so stdout is deterministic.

### 4.1. Project Structure

```text
record-application-events-demo/
├── pom.xml
└── src/test/java/example/events/RecordApplicationEventsTest.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>record-application-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.9</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
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
```

`spring-test` contains `@RecordApplicationEvents` and `ApplicationEvents`. `junit-jupiter` provides the JUnit 5 API and test engine; `maven-surefire-plugin` runs tests matching the `*Test` naming pattern. You do not need to create a Spring Boot application to test this event-recording mechanism.

### 4.3. src/test/java/example/events/RecordApplicationEventsTest.java

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(RecordApplicationEventsTest.TestConfig.class)
@RecordApplicationEvents
class RecordApplicationEventsTest {

    record OrderPlaced(String orderId, String customerId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void placeOrder(String orderId) {
            publisher.publishEvent(new OrderPlaced(orderId, "C-7"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Autowired
    OrderService service;

    @Test
    void recordsDomainEventsAndCanClearThem(ApplicationEvents events) {
        // No OrderPlaced recorded before the operation.
        assertEquals(0L, events.stream(OrderPlaced.class).count());

        service.placeOrder("PO-42");

        List<OrderPlaced> first = events.stream(OrderPlaced.class).toList();
        assertEquals(1, first.size());
        assertEquals("PO-42", first.get(0).orderId());
        assertEquals("C-7", first.get(0).customerId());
        System.out.println("recorded: " + first.get(0).orderId());

        // Clears only the events held by the recorder.
        events.clear();

        long afterClear = events.stream(OrderPlaced.class).count();
        assertEquals(0L, afterClear);
        System.out.println("after clear: " + afterClear);

        service.placeOrder("PO-43");

        List<OrderPlaced> second = events.stream(OrderPlaced.class).toList();
        assertEquals(1, second.size());
        assertEquals("PO-43", second.get(0).orderId());
        System.out.println("recorded: " + second.get(0).orderId());
    }
}
```

From the directory containing `pom.xml`, **JDK 17+** and **Maven** are required:

```bash
mvn -q test
```

The lines printed by the test itself appear in this order, excluding Maven/JUnit/Spring logs:

```text
recorded: PO-42
after clear: 0
recorded: PO-43
```

The test must complete successfully (Maven exit code 0); if an assertion fails, Maven Surefire reports test failed.

**Why does the example work?**

1. `@SpringJUnitConfig` creates the Spring test context and registers `SpringExtension` for JUnit 5. `TestConfig` provides `OrderService` as a Spring bean.
2. `@RecordApplicationEvents` activates the recorder via `ApplicationEventsTestExecutionListener`. This listener is normally included in the default `TestExecutionListeners` list.
3. `service.placeOrder("PO-42")` calls the real `ApplicationEventPublisher.publishEvent(...)`; Spring records the `OrderPlaced` payload.
4. The test method receives `ApplicationEvents` via parameter injection. `events.stream(OrderPlaced.class)` filters the exact domain event, checking count and fields.
5. `events.clear()` empties the recorder's buffer in the current method. Subsequent publishing of `PO-43` yields only one new event in the list observed by the test.
6. The test **has no business listener**. This is intentional to demonstrate that `@RecordApplicationEvents` observes **publication**, without requiring a listener to handle the business event.

If some Spring lifecycle events exist in the test context, they **do not break** the assertions because the test filters strictly on `OrderPlaced.class`.

## 5. Using with @SpringBootTest

In a Spring Boot application, the annotation still comes from `spring-test` and can be combined with `@SpringBootTest`, for example:

```java
@SpringBootTest
@RecordApplicationEvents
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void publishesCheckoutCompleted(ApplicationEvents events) {
        checkoutService.checkout("CHK-42");

        assertEquals(1L,
                events.stream(CheckoutCompleted.class).count());
    }
}
```

This is an **illustrative integration snippet**, not standalone: the application must provide `CheckoutService`, `CheckoutCompleted`, `@SpringBootTest`, and necessary imports. Spring Boot test dependencies are normally supplied by `spring-boot-starter-test`. You do not need to declare an `ApplicationEvents` bean manually in production configuration.

You can add assertions for payload contents:

```java
List<CheckoutCompleted> captured =
        events.stream(CheckoutCompleted.class).toList();

assertEquals("CHK-42", captured.get(0).checkoutId());
```

Do not merely count events when critical parts of the contract are identifiers, versions, timestamps, or business state. However, avoid asserting unstable values like `Instant.now()` down to the exact nanosecond; inject a controllable `Clock` into the service or check a reasonable time range.

### Compared with Mocking ApplicationEventPublisher

| Testing Approach | Best Verifies | Does Not Prove |
| --- | --- | --- |
| Mockito `verify(publisher).publishEvent(...)` | Whether the service called the right publish API | Whether a real Spring context emitted the event |
| `@RecordApplicationEvents` + `ApplicationEvents` | Spring context recorded events of the right type/payload/count | Listeners finished processing, transaction committed |
| Spy/mock listener or checking side effects | A specific listener executed its work | All other events were also processed |
| Database/outbox integration test | Durable changes and commit/rollback | Out-of-JVM consumer received the message |

Choose the test matching the **actual contract** you need to protect. If testing pure Java domain models, there is no need to start a Spring context; if testing real Spring event publication, `@RecordApplicationEvents` is the right tool.

## 6. Watch Out for @Transactional in Tests: Recorded Event Does Not Mean Committed

This is one of the biggest traps when using `@RecordApplicationEvents`.

Suppose a service publishes `OrderPlaced` inside a transaction and has a listener:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    notificationService.notifyCustomer(event.orderId());
}
```

This snippet is **an integration illustration only**. `@TransactionalEventListener` binds listener execution to **the successful commit phase**, not the moment `publishEvent(...)` is merely invoked.

In Spring TestContext, an `@Transactional` test method is usually **automatically rolled back** when the test finishes. Therefore, the following can happen:

```text
@Transactional test starts transaction T1
       |
       +-- service.placeOrder(...)
       |      +-- publishEvent(OrderPlaced)
       |             +-- @RecordApplicationEvents records the event
       |             +-- @TransactionalEventListener(AFTER_COMMIT) registers callback
       |
       +-- events.stream(OrderPlaced.class).count() == 1
       |
       +-- test finishes
              +-- T1 is ROLLED BACK by default
              +-- AFTER_COMMIT DOES NOT RUN
```

Hence, seeing the event in `ApplicationEvents` **does not prove** the after-commit side effect ran. To test an `AFTER_COMMIT` listener, ensure the transaction actually commits before asserting side effects.

Appropriate approaches:

1. Use a test **without a test-managed `@Transactional`** wrapping it, calling the transactional service through its Spring proxy so the service commits on return, then check side effects.
2. Inside an intentional test transaction, use `TestTransaction.flagForCommit()` and `TestTransaction.end()` to finish with a commit before asserting side effects. This is a `spring-test` utility and works only when a valid test-managed transaction is active.
3. Use `@Commit` or `@Rollback(false)` if you want the test transaction to commit after the test method, **but do not assert after-commit side effects inside the method body before the framework commits**; use an appropriate lifecycle hook or test structure.
4. Once test data has been committed, manage **cleanup/isolation** explicitly so data does not pollute subsequent tests.

Do not call `flush()` or `saveAndFlush()` and treat that as commit: flushing sends SQL to the database, yet the transaction can still roll back. Likewise, `events.clear()` has zero effect on commit.

### Does @RecordApplicationEvents Also Record Events from Rolled-Back Transactions?

It can record an event **published within a transaction**, even if that transaction later rolls back. The recorder observes Spring event **publication**, rather than filtering only events belonging to committed transactions. If the requirement is "only record after commit," design the event or listener around the transaction phase and verify the corresponding outcome instead of inferring from the recorder.

With `AFTER_ROLLBACK`/`AFTER_COMPLETION` listeners, distinguish between the event being published and the callback firing after the transaction ends. A test with `@Transactional` and auto-rollback may cause some rollback callbacks to run **after assertions in the test body have already completed**. Test this phase at an exact synchronization point rather than using arbitrary delays.

## 7. Can @RecordApplicationEvents Observe Asynchronous Events?

Per the Spring TestContext contract, the recorder is tied to **the test method lifecycle** and test execution mechanism. Javadoc describes recording events published from the test thread **or child threads** within supported bounds. However, this annotation cannot be treated as a global collector for **every thread from an executor pool or every process**.

For example:

```java
@Async("eventExecutor")
public void publishLater(String orderId) {
    applicationEventPublisher.publishEvent(new OrderPlaced(orderId));
}
```

This is an **illustrative integration snippet**, not standalone: it requires `@EnableAsync`, the `eventExecutor` bean, and related classes. `publishLater(...)` might execute after the test body has already checked the recorder, or on an executor thread without the same test-scoped recording context. `events.stream(...)` may then miss the event or fail to reflect the complete async flow.

To test async reliably:

- **Wait for real completion:** `CompletableFuture`, latches, or a controlled test executor; never use `Thread.sleep(...)` hoping the event has emitted.
- **Check context boundaries:** was the event published in the same Spring context and within the current method lifecycle? Does the executor thread receive the proper context?
- **Separate assertions:** if the goal is confirming an async listener executed a side effect, check the side effect/spy or durable state after completion rather than relying solely on the event recorder.
- **For out-of-JVM brokers:** use dedicated broker and consumer contract/integration tests; `@RecordApplicationEvents` does not capture Kafka/RabbitMQ messages automatically.
- **Do not tie tests to unguaranteed thread ordering:** the recorder is not a scheduler or delivery-order specification.

If a test requires every async event to be captured deterministically, you can control the executor in tests, switch a measured flow to synchronous, or design appropriate synchronization points/hooks. Never "fix" flaky tests with longer sleeps.

## 8. Combining with @EventListener: Recording Publication Differs from Verifying Handling

Suppose there is a listener:

```java
@Component
class OrderAccountingListener {

    private final AccountingService accounting;

    OrderAccountingListener(AccountingService accounting) {
        this.accounting = accounting;
    }

    @EventListener
    void on(OrderPlaced event) {
        accounting.recordRevenue(event.orderId());
    }
}
```

This is an **illustrative snippet**, assuming `OrderPlaced` and `AccountingService` exist.

A solid integration test can:

1. Call the service emitting `OrderPlaced`.
2. Assert `events.stream(OrderPlaced.class)` contains the right event and payload.
3. Assert `accounting` (spy/mock) was invoked or the database was updated per the contract.
4. If async, explicitly await completion before asserting step 3.
5. If transaction-bound, assert at the moment the transaction actually completes.

If you only check `events.stream(...)`, the test still passes even if `OrderAccountingListener` was never registered, skips the event conditionally, or fails on another thread. **Checking publication and checking consumption should be two independent assertions**.

### Event Counts and Duplication

`ApplicationEvents.stream(OrderPlaced.class).count()` counts how many times matching events were saved by the recorder. If one action emits two events of the same type, the count can be 2. However, publisher call counts **do not always** equal the number of business tasks with final effects: a listener can retry, emit secondary events, or an application context hierarchy can propagate events to parent contexts.

To catch duplicate emission bugs:

- Check `eventId` and stable business identifiers when the contract requires uniqueness.
- Do not assert only `count() > 0` when the contract requires exactly **one** event.
- If verifying event order in a synchronous flow, collect the stream in recorded order and compare; do not apply completion-order expectations to async listeners.
- Call `events.clear()` before the measured action when you want to exclude same-type events from `@BeforeEach` or setup steps, but never clear in a way that hides unwanted publishing during setup.

## 9. Custom @TestExecutionListeners Can Break the Recorder

`ApplicationEventsTestExecutionListener` is one of Spring's **default registered** `TestExecutionListener` implementations. When a test uses `@TestExecutionListeners` to replace the default list without merging, the recording listener can be dropped.

Example *illustrating configuration requiring care*:

```java
@TestExecutionListeners(
        listeners = CustomTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

This code requires `CustomTestExecutionListener` and annotation imports. `MERGE_WITH_DEFAULTS` preserves the default framework listeners, including the recorder, while adding your custom listener. If you intentionally replace the entire list, you must register `ApplicationEventsTestExecutionListener` properly as required by the framework.

When the annotation is present yet `ApplicationEvents` cannot be injected, check:

- Is the test running via `SpringExtension`/TestContext framework?
- Is `@RecordApplicationEvents` placed on the class or an appropriate meta-annotation?
- Did a custom `@TestExecutionListeners` drop the defaults?
- Is `ApplicationEvents` being injected into a constructor or singleton outside the test method lifecycle?
- Are you checking events from a different context, process, or async thread outside the recorder's scope?

Do not fix this by creating an arbitrary production `ApplicationEvents` bean; it does not replace `ApplicationEventsTestExecutionListener`.

## 10. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`@RecordApplicationEvents` is only for Spring Boot" | Belongs to **Spring Framework TestContext**; Spring Boot is one environment that uses it |
| "The annotation auto-creates a business listener" | It records publication; it does not replace application listeners |
| "`stream(OrderPlaced.class)` counts all Spring lifecycle events" | It filters only events or payloads matching type `OrderPlaced` |
| "`stream()` directly returns every published POJO" | The no-arg API returns `Stream<ApplicationEvent>`; POJOs usually reside inside `PayloadApplicationEvent` |
| "`clear()` rolls back the database" | It only clears events held by the recorder |
| "Test has the event -> `AFTER_COMMIT` listener ran" | No; test transactions usually roll back by default |
| "Test has the event -> external message was sent" | No; broker/outbox needs separate assertions |
| "Every thread is recorded" | Not guaranteed for executor pools or other processes |
| "`@RecordApplicationEvents` completely replaces Mockito" | It only measures real publication; mocks/spies serve different roles |
| "No event in stream guarantees the service didn't publish" | Check recorder lifecycle, context, thread, event type, and test setup |
| "Adding `@RecordApplicationEvents` without `SpringExtension` still works" | Requires Spring TestContext support |
| "`ApplicationEvents` can be injected via test class constructor" | Improper; the dependency is scoped per test method |

## 11. Practical Testing Strategy

A resilient test suite for a system using Spring events can be layered:

**Domain / service unit tests:** Test event emission conditions and payloads using a fake/mocked publisher or domain event collector; no Spring context needed when not testing event multicasting.

**Spring integration tests with `@RecordApplicationEvents`:** Verify events published by Spring-managed services/repositories—type, count, content, and forbidden events. Do not infer commit from publication.

**Listener integration tests:** Confirm `@EventListener` registration, `condition` filters, `@Order` when relevant, side effects, and error propagation. If the listener is async, await completion; if transaction-bound, commit/roll back per the use case.

**Transaction/outbox tests:** Write data and outbox events in the same transaction, simulate rollback, read from a fresh connection, and verify durability. When real delivery is needed, add separate broker/consumer, idempotency, and retry tests.

For Spring Boot tests where context startup is costly, use `@SpringJUnitConfig` with minimal configuration for tests that only need the event bus; use `@SpringBootTest` when you want auto-configuration or full production wiring.

### A Checklist Before Accepting a Test

1. Does the test have `@RecordApplicationEvents` on the right class with `SpringExtension`/TestContext active?
2. Does it assert **event type + payload + count**, not just "at least one," when the contract requires exactness?
3. Does it avoid confusing framework lifecycle events with domain events?
4. Is `ApplicationEvents` handled within the proper test-method lifecycle?
5. If transactions are involved, does it distinguish publication from commit and listener phases?
6. If async is involved, is there an explicit synchronization point instead of sleep?
7. If listener side effects matter, are there assertions independent of the event recorder?
8. If custom `@TestExecutionListeners` is used, is the recorder listener preserved?
9. Is data leakage between tests and across Spring contexts avoided?
10. Are event IDs/source data used to detect duplicates when business rules require it?

## 12. Self-Assessment Questions

**1. Which library provides `@RecordApplicationEvents`?**  
It belongs to Spring Framework's `spring-test`, package `org.springframework.test.context.event`. It works in Spring Boot but is not a Boot-only API.

**2. Which API counts published `OrderPlaced` events in a test?**  
`events.stream(OrderPlaced.class).count()`; it filters both matching event types and payloads.

**3. Why shouldn't you assert `events.stream().count() == 1`?**  
Because the no-arg stream includes every `ApplicationEvent` collected by the recorder, which can include framework events and other non-business events.

**4. What does `events.clear()` clear?**  
It clears the event history **recorded in the current recorder**; it does not delete data or undo side effects.

**5. A `@Transactional` test records the event and has an `AFTER_COMMIT` listener. Why didn't the listener run?**  
Because Spring test transactions roll back by default when the test finishes; the published event is still recorded, yet no successful commit occurred.

**6. Can `ApplicationEvents` be injected into a test class constructor?**  
Not appropriately; the dependency has test-method lifecycle scope. Use a `@Test`/lifecycle method parameter or an `@Autowired` field.

**7. Why shouldn't async tests rely solely on `@RecordApplicationEvents`?**  
The recorder is scoped to a test lifecycle and specific context/threads; async events may arrive late or outside that context. Synchronization points and separate side-effect assertions are required.

**8. Does `@RecordApplicationEvents` automatically persist events to Kafka or an outbox?**  
No. It is an **in-memory Spring application event publication testing** tool, not production delivery infrastructure.

## 13. Official Documentation

- [Spring Framework Reference — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework Reference — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework Javadoc — `RecordApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html)
- [Spring Framework Javadoc — `ApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework Reference — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide — Spring Integration Using JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/)

