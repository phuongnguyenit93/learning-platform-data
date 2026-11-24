# ApplicationEventsTestExecutionListener: Recording and Testing Spring Application Events

## 1. Concept and Goals

`ApplicationEventsTestExecutionListener` is a class in the **Spring TestContext Framework**, with the fully qualified name:

`org.springframework.test.context.event.ApplicationEventsTestExecutionListener`

It is a `TestExecutionListener` that supports recording application events published in the `ApplicationContext` **within the scope of a single test method**, allowing the test to query recorded events via the `ApplicationEvents` API.

This is a **testing** mechanism; it is not a business listener bean using `@EventListener`. In most Spring TestContext projects, this class is **registered by default**. However, simply having the listener class registered is not enough: the test class must be annotated with **`@RecordApplicationEvents`**, otherwise the event-recording listener effectively does nothing.

After this lesson, you should be able to:

1. Understand the role of `ApplicationEventsTestExecutionListener` in the Spring testing lifecycle.
2. Enable it with `@RecordApplicationEvents` and obtain `ApplicationEvents` in JUnit Jupiter.
3. Inspect POJO/`ApplicationEvent` events, filter by type, match payloads, and reset records with `clear()`.
4. Run a Java 17+ project with real JUnit 5 tests.
5. Distinguish the listener that **records events** from the listener that **publishes test execution events**.
6. Avoid pitfalls involving custom `@TestExecutionListeners`, test-method scope, transactions, async, and context caching.

## 2. Classes and Annotations to Distinguish

| Component | Package or Role |
| --- | --- |
| `ApplicationEventsTestExecutionListener` | Spring TestContext infrastructure; manages event-recording capability for tests |
| `@RecordApplicationEvents` | Annotation on the **test class**, instructing Spring TestContext to record events |
| `ApplicationEvents` | API for tests to query/read/clear recorded events |
| `ApplicationEventPublisher` | Application API used to **publish** events |
| `@EventListener` | Method in a Spring bean used to **handle** events |
| `EventPublishingTestExecutionListener` | A **different** listener: publishes test lifecycle events such as `BeforeTestMethodEvent` |
| `SpringExtension` | Connects JUnit Jupiter with Spring TestContext |
| `@SpringJUnitConfig` | Convenience annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration` |

**Easily confused name:** `ApplicationEventsTestExecutionListener` is not an `ApplicationListener<OrderCreated>`. It does not run your business logic. It helps **the test observe what was published**.

Do not instantiate `new ApplicationEventsTestExecutionListener()` and call `publishEvent` as though it were an event bus. The event bus is `ApplicationContext` / `ApplicationEventPublisher`, whereas `TestExecutionListener` is managed by the TestContext framework.

## 3. Execution Mechanism in TestContext

General flow when JUnit 5 runs a test:

~~~text
JUnit Jupiter
   |
   +-- SpringExtension
         |
         +-- TestContextManager / list of TestExecutionListeners
         |
         +-- ApplicationEventsTestExecutionListener (default)
         |       checks @RecordApplicationEvents
         |       registers ApplicationEvents for the current test
         |
         +-- create/inject test instance, prepare test method
         |
         +-- @BeforeEach and @Test
         |       |
         |       +-- service calls publisher.publishEvent(...)
         |       +-- ApplicationEvents records published event
         |       +-- test calls events.stream(OrderCreated.class)
         |
         +-- @AfterEach, end of test lifecycle
                 |
                 +-- clean up test-specific recording state
~~~

This is a **conceptual diagram**, not an exact list of every JUnit callback or the ordering of every `TestExecutionListener`. For instance, `prepareTestInstance`, `beforeTestMethod`, `beforeTestExecution`, and cleanup callbacks belong to distinct TestContext phases.

The key point is that `ApplicationEvents` is scoped to **the current test method's lifecycle**, not a JVM-wide event store or suite-wide singleton bean. One test should never have to filter out business events emitted by a preceding test.

### 3.1. When Is the Listener Registered?

Spring registers `ApplicationEventsTestExecutionListener` in the **default** set of `TestExecutionListener`s. Usually you only need:

~~~java
@SpringJUnitConfig
@RecordApplicationEvents
class MyEventTests {
    // @Test methods use ApplicationEvents.
}
~~~

In Spring Framework 6.2.x, this listener has `ORDER = 1800` (since 6.2.3) and is ordered after `DirtiesContextBeforeModesTestExecutionListener` and before the relevant injection listeners. Do not rely on an arbitrary order number to manually control event capturing unless you genuinely need a custom TestContext setup.

### 3.2. When Does It Not Record?

`@RecordApplicationEvents` can be placed directly or via a **meta-annotation** on the test class. Without that annotation, even an already-registered `ApplicationEventsTestExecutionListener` will not activate normal recording.

If you use a custom `@TestExecutionListeners` and **replace** all default listeners, `ApplicationEventsTestExecutionListener` may no longer be registered. In that case, merely adding `@RecordApplicationEvents` is not enough; you must merge the default listeners or explicitly register the missing listener.

## 4. Prerequisites for Usage

With JUnit Jupiter, the typical setup is:

1. Include `spring-test` and JUnit Jupiter in test dependencies.
2. Run the test class via `SpringExtension`; the shortest way is `@SpringJUnitConfig` with configuration containing the Spring beans under test.
3. Place `@RecordApplicationEvents` on the class.
4. Keep `ApplicationEventsTestExecutionListener` in the `TestExecutionListeners` list (present by default).
5. Receive `ApplicationEvents` via a parameter in `@Test`, `@BeforeEach`, or `@AfterEach`, or via an `@Autowired` field.
6. Run the use case that makes Spring publish events, then assert `events.stream(...)`.

Example test method declaration:

~~~java
// Illustrative; OrderService, OrderSubmitted, and test config defined separately.
@Test
void shouldPublishOrderSubmitted(
        @Autowired OrderService service,
        ApplicationEvents events) {

    events.clear(); // ignore unrelated events recorded before the action
    service.submit(101L);

    assertEquals(
            1L,
            events.stream(OrderSubmitted.class).count());
}
~~~

`ApplicationEvents` is provided by Spring TestContext during the test lifecycle, while `OrderService` is injected by Spring as a parameter via `@Autowired`. `clear()` is optional, though useful when you want to measure **only the events produced by a specific action**, without noise from framework or test-fixture events published earlier.

### Why Is Constructor Injection Not Appropriate?

Spring documentation notes that `ApplicationEvents` is a resolvable dependency scoped to the **test method**. It is unavailable outside that lifecycle and **cannot be `@Autowired` into a test class constructor**. Do not store an `ApplicationEvents` instance obtained from a constructor and treat it as a singleton.

The recommended approach is an `ApplicationEvents events` parameter on `@Test`, `@BeforeEach`, or `@AfterEach`. An `@Autowired ApplicationEvents` field on the test class is also supported during the test lifecycle, though parameter injection makes the lifetime boundary clearer.

`@BeforeAll` and `@AfterAll` sit outside each test method's lifecycle; do not design current-test event recording around injecting `ApplicationEvents` in these class-level hooks.

## 5. The `ApplicationEvents` API

The `org.springframework.test.context.event.ApplicationEvents` interface supports three core methods:

| API | Meaning |
| --- | --- |
| `Stream<ApplicationEvent> stream()` | Obtains a stream of recorded `ApplicationEvent`s |
| `<T> Stream<T> stream(Class<T> type)` | Filters by event type or **payload** type and returns matching objects |
| `void clear()` | Clears events recorded in the current instance; subsequent new events are still recorded |

### 5.1. Inspecting Events Passed as POJOs

Since Spring Framework 4.2, `ApplicationEventPublisher.publishEvent(Object)` can accept a POJO or record that does not extend `ApplicationEvent`:

~~~java
// Illustrative inside a Spring-managed service.
publisher.publishEvent(new OrderSubmitted(101L));
~~~

When publishing a POJO, Spring may wrap the payload in `PayloadApplicationEvent` for delivery. Thus `events.stream()` returns `ApplicationEvent` objects including the wrapper, whereas:

~~~java
List<OrderSubmitted> submitted =
        events.stream(OrderSubmitted.class).toList();
~~~

...gives you the **`OrderSubmitted` payloads** of the right type. This is a clean way to assert domain events without depending on wrapper details.

### 5.2. When to Use the No-Arg `stream()`?

When you need to check the existence of a raw `ApplicationEvent`, inspect wrappers, or observe multiple event types:

~~~java
// Illustrative inside @Test, after events have been emitted.
boolean sawPayloadWrapper = events.stream()
        .anyMatch(event -> event instanceof PayloadApplicationEvent<?>);
~~~

Note: the full event stream may contain **test execution events** or other framework events. Do not assert that total `events.stream().count()` equals 1 just because you called `OrderService.submit()` once. Filtering by the exact domain event type is a much more reliable verification.

### 5.3. Clearing Events Before a Specific Action

~~~java
events.clear();
service.submit(101L);
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

`clear()` **only deletes recorded data** inside `ApplicationEvents`; it does not clear any queue, cancel published events, roll back transactions, or unregister `@EventListener`s from the context.

`stream()` returns a Java `Stream`: if you want to perform multiple operations, call `stream(...)` fresh each time or materialize it into a `List`; a consumed `Stream` cannot be reused.

## 6. Complete Java 17+ Example: JUnit 5 Recording Domain Events

This example uses:

- Java 17+ and Maven.
- Spring Framework **6.2.12**: `spring-context` and `spring-test`.
- JUnit Jupiter **5.11.4** and Maven Surefire **3.5.2**.
- An `OrderService` Spring bean publishing an `OrderSubmitted` record via `ApplicationEventPublisher`.
- A test class configured with `@SpringJUnitConfig` and `@RecordApplicationEvents`.
- Two independent test methods verifying `stream(Class)`, `stream()`, and `clear()`.

No Spring Boot, web server, or database is required; this example focuses on **Spring TestContext** and `ApplicationEventsTestExecutionListener`.

Directory structure:

~~~text
application-events-test/
├── pom.xml
└── src/test/java/demo/OrderEventTests.java
~~~

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-events-test</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.12</version>
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
~~~

### 6.2. `src/test/java/demo/OrderEventTests.java`

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(classes = OrderEventTests.Config.class)
@RecordApplicationEvents
class OrderEventTests {

    // POJO/record payload: does not extend ApplicationEvent.
    record OrderSubmitted(long orderId) {}

    static final class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void submit(long orderId) {
            publisher.publishEvent(new OrderSubmitted(orderId));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Test
    void recordsTypedPayload(
            @Autowired OrderService service,
            ApplicationEvents events) {

        // Do not let events from test preparation interfere with assertions.
        events.clear();

        service.submit(101L);

        List<OrderSubmitted> recorded =
                events.stream(OrderSubmitted.class).toList();

        assertEquals(List.of(new OrderSubmitted(101L)), recorded);

        // POJOs are wrapped by Spring in an ApplicationEvent wrapper.
        assertTrue(events.stream().anyMatch(
                event -> event instanceof PayloadApplicationEvent<?>));
    }

    @Test
    void clearOnlyResetsTheRecording(
            @Autowired OrderService service,
            ApplicationEvents events) {

        events.clear();
        service.submit(201L);

        assertEquals(1L, events.stream(OrderSubmitted.class).count());

        // Clears recorded test data without stopping ApplicationEventPublisher.
        events.clear();
        assertEquals(0L, events.stream(OrderSubmitted.class).count());

        service.submit(202L);

        assertEquals(
                List.of(new OrderSubmitted(202L)),
                events.stream(OrderSubmitted.class).toList());
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expected outcome:** Maven Surefire finds class `OrderEventTests` and executes **2 tests**, all PASS (`Tests run: 2, Failures: 0, Errors: 0, Skipped: 0`). Log lines/display order may vary by Maven/JUnit and environment; there is no `System.out.println` in the tests, so there is no custom stdout to match line by line.

### 6.3. Why Does the Example Work?

- `@SpringJUnitConfig` enables `SpringExtension` and builds an `ApplicationContext` from `Config`.
- `Config` declares an `OrderService`, while Spring supplies the appropriate `ApplicationEventPublisher` for the bean.
- `@RecordApplicationEvents` tells TestContext to record events.
- `ApplicationEventsTestExecutionListener` is already in the default listeners, so the test **does not need to register the listener manually**.
- JUnit invokes the test method; Spring resolves `@Autowired OrderService` and `ApplicationEvents` parameters.
- When `service.submit` publishes an `OrderSubmitted` record, TestContext records that event.
- `stream(OrderSubmitted.class)` extracts the exact payload even though Spring wrapped the event inside `PayloadApplicationEvent`.
- The second test shows that `clear()` erases earlier recorded data while events published afterward are still newly added.

The two tests **do not depend on execution order**. Neither `@TestMethodOrder` nor static fields are used to rely on an earlier test's outcome. Each test clears before its action, so even when TestContext emits other test-lifecycle events, assertions on `OrderSubmitted` remain independent.

## 7. `@RecordApplicationEvents` and Per-Test-Method Lifecycle

### 7.1. Test Class, Not Individual Listener Beans

`@RecordApplicationEvents` is placed on the **test class** (and can also be used as a meta-annotation). It instructs **Spring TestContext** to record events while tests execute. You do not need to put this annotation on `OrderService` or business beans.

When another test class lacks the annotation, the fact that the listener infrastructure still exists in the default configuration **does not mean that class automatically receives `ApplicationEvents` for assertions**.

### 7.2. Using in `@BeforeEach` and `@AfterEach`

Spring allows receiving `ApplicationEvents` in **per-test** lifecycle methods:

~~~java
// Illustrative in a test class with @SpringJUnitConfig and @RecordApplicationEvents.
@BeforeEach
void resetEventRecording(ApplicationEvents events) {
    events.clear();
}

@Test
void someTest(ApplicationEvents events) {
    // Perform action and assert events.
}

@AfterEach
void inspectEvents(ApplicationEvents events) {
    // Can inspect events emitted during the test or earlier steps.
}
~~~

This is an illustrative snippet; it requires `@BeforeEach`, `@Test`, `@AfterEach` imports and real Spring test configuration. Note that events may be published during `@BeforeEach` or `@AfterEach`; choose where to place `clear()` and when to assert accordingly.

### 7.3. `@Autowired` Field

Another option is field injection in the test class:

~~~java
// Illustrative: inside a test class annotated with @RecordApplicationEvents.
@Autowired
ApplicationEvents applicationEvents;
~~~

Spring documentation supports this approach, yet **discourages constructor injection** for `ApplicationEvents` because its actual scope is the test method. If you want to avoid lifecycle misunderstandings, a method parameter is usually more explicit.

### 7.4. Test Context Cache Is Not a Test Event Store

Spring TestContext can cache an `ApplicationContext` shared across multiple test methods or test classes with identical configuration. That **does not mean** `ApplicationEvents` is a list retaining every event from all tests sharing the context.

The recorder is managed per the **current test's** lifecycle, whereas singleton beans or database test fixtures themselves may still be reused. Do not infer that isolated event recording means every other state in the application context resets automatically; tests must still manage shared data and isolate side effects.

## 8. Custom `@TestExecutionListeners`: Common Configuration Pitfall

Per Spring documentation, `ApplicationEventsTestExecutionListener` **is registered by default**, so normally no explicit declaration is needed. However, if you configure:

~~~java
// Risk illustration: MyCustomListener must be defined.
@TestExecutionListeners(MyCustomListener.class)
class MyCustomTests {
}
~~~

...if this configuration **replaces default listeners**, application event recording can disappear, even though `@RecordApplicationEvents` remains. Preserve the default listeners with the appropriate merge mode:

~~~java
// Illustration: MyCustomListener must be defined.
@TestExecutionListeners(
    listeners = MyCustomListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class MyCustomTests {
}
~~~

Then the custom listener is merged with the default set, including `ApplicationEventsTestExecutionListener`. If a project has a hierarchy or multiple meta-annotations, verify how `TestExecutionListeners` configurations merge and their exact ordering rather than looking only at one local annotation.

**Another anti-pattern:** manually reconfiguring the entire listener list and forgetting `DependencyInjectionTestExecutionListener`. In that case, not only can `ApplicationEvents` fail, injecting beans into the test class can break as well.

## 9. Distinguishing from `EventPublishingTestExecutionListener`

Two classes are very easy to confuse because both contain "Event" and "TestExecutionListener":

| Characteristic | `ApplicationEventsTestExecutionListener` | `EventPublishingTestExecutionListener` |
| --- | --- | --- |
| Purpose | **Records** application events for test assertions | **Publishes** test lifecycle events into the Spring `ApplicationContext` |
| Main activation use case | `@RecordApplicationEvents` | Interacting with test lifecycle and an already-loaded context |
| API used in tests | `ApplicationEvents.stream(...)`, `clear()` | Listener beans receiving `BeforeTestMethodEvent`, `AfterTestMethodEvent`, etc. |
| Is it an `@EventListener` bean? | No | No; it is an infrastructure `TestExecutionListener` itself |
| Included in default listeners? | Yes | Yes |

Test execution events published by `EventPublishingTestExecutionListener` include `BeforeTestClassEvent`, `PrepareTestInstanceEvent`, `BeforeTestMethodEvent`, `BeforeTestExecutionEvent`, `AfterTestExecutionEvent`, `AfterTestMethodEvent`, and `AfterTestClassEvent`.

Not **every** test lifecycle event always appears: the test execution event publisher can only publish when the `ApplicationContext` has already been loaded; depending on caching and when the context is built, certain class-level events may not fire. Therefore, when testing a single domain event, **filter by the domain event type** rather than asserting a raw total event count.

Example of a Spring bean listening to a test execution event:

~~~java
// Conceptual illustration; requires imports and appropriate Spring bean declaration.
@EventListener
public void onBeforeTestMethod(BeforeTestMethodEvent event) {
    // Runs when Spring TestContext emits the corresponding test execution event.
}
~~~

Do not use `EventPublishingTestExecutionListener` as a way to "enable recording domain events"; it solves a different job.

## 10. Limitations When Testing Events

### 10.1. Recording an Event Differs from Confirming Listener Success

An assertion:

~~~java
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

...proves `OrderSubmitted` was recorded in the test context. It **does not prove on its own** that an email was sent, the database committed, `@Async` listeners completed, or a broker received an integration event.

To verify listener **side effects**, write dedicated tests: check repository state, mock interactions, message stubs, or processing results, with appropriate synchronization/timeouts.

### 10.2. POJO Events and Payload Wrappers

`ApplicationEvents.stream(Class<T>)` can return event objects or event **payloads** matching the given type. For POJO records, use `stream(OrderSubmitted.class)`, and do not assume you can write `stream().map(event -> (OrderSubmitted) event)` because a `PayloadApplicationEvent` is not directly an `OrderSubmitted` object.

If you create a subclass of `ApplicationEvent`, `stream(MyApplicationEvent.class)` can also filter by that event type. Pick an explicit typed check rather than asserting class names via strings.

### 10.3. Transactions and `@TransactionalEventListener`

When a method publishes an event **inside a transaction**, recording can see the event immediately upon publish. Yet `@TransactionalEventListener(phase=AFTER_COMMIT)` runs **only if the transaction commits successfully**. The two facts do not contradict each other: the event was published and recorded, while the transaction-bound callback may never execute.

If a test has `@Transactional` managed by Spring TestContext, the test transaction **usually rolls back by default**. Do not assert `AFTER_COMMIT` ran just because `events.stream(MyEvent.class)` contains the event. To test after-commit callbacks, structure an explicit transaction commit—for example testing with a real transaction and `TestTransaction` where appropriate.

Likewise, `ApplicationEventsTestExecutionListener` does not replace `TransactionalTestExecutionListener` and does not alter commit/rollback semantics.

### 10.4. Async and Thread Boundaries

`@RecordApplicationEvents` records events emitted within test scope according to test-thread and supported child-thread management. However, a task running in a **pre-existing thread pool**, a scheduler, an external worker, or another process **does not automatically belong to the test's recording context**.

If an event is published from an executor/background worker, do not assume `ApplicationEvents` definitely observes every publish on that thread. Verify whether the recording context is propagated properly; prefer tests with explicit synchronization or publish from the test thread when the goal is solely unit/integration testing the publisher.

Conversely, `ApplicationEvents` recording the **source event** does not mean `@Async @EventListener` handlers have finished processing. Use `CountDownLatch`, `CompletableFuture`, Awaitility, or a timeout-bounded wait utility when asserting async side effects. Never rely on arbitrary `Thread.sleep` to prove correctness.

### 10.5. Counting, Ordering, and Duplicates

- Filter by the exact domain event class to avoid infrastructure events skewing total counts.
- Do not infer async listener completion order from event stream order.
- If an action emits multiple events of the same type, filter further by `aggregateId`, `eventId`, or payload to avoid false positives.
- With parent/child `ApplicationContext`s, events may propagate upward to the parent; understand context scope and avoid "exactly once" assumptions in systems with propagation.
- For brokers or out-of-JVM applications, `ApplicationEvents` in Spring tests is not a distributed message collector; use broker/integration-adapter test harnesses.

## 11. Diagnostic Checklist When `ApplicationEvents` Has No Data

1. **Does the test class have `@RecordApplicationEvents`?** Place the annotation on the class or a meta-annotation, not just on a service bean.
2. **Is the test running with Spring TestContext?** With JUnit 5, use `@SpringJUnitConfig`, `@SpringBootTest` with `SpringExtension`, or an equivalent configuration.
3. **Is `ApplicationEventsTestExecutionListener` in the listener set?** Included by default unless a custom `@TestExecutionListeners` replaced the defaults.
4. **Is `ApplicationEvents` injected in the right lifecycle?** Use a test method / `@BeforeEach` / `@AfterEach`; do not try to inject it into the constructor.
5. **Was the event actually published inside the test's ApplicationContext?** If code creates an object outside Spring without using Spring's publisher, recording cannot synthesize events.
6. **Are you filtering by the right type?** For POJO payloads use `stream(PayloadType.class)`, not an invalid cast from `ApplicationEvent`.
7. **Did you call `clear()` after publishing and before asserting?** That erases the test's own recording.
8. **Did publishing happen on another thread?** An executor may not carry the recording context to worker threads.
9. **Are you confusing event publication with listener completion?** Async side effects and transactional callbacks must be verified separately.
10. **Does the context have a hierarchy or multiple listeners?** Check emission sources, duplicates, and appropriate lifecycle timing.

## 12. Advanced Practice

### Exercise 1 — Filtering Events by Content

Extend `OrderSubmitted` to:

~~~java
// Illustrative Java 17 record:
record OrderSubmitted(long orderId, String customerId) {}
~~~

After submitting two orders, filter `events.stream(OrderSubmitted.class)` and use `filter(e -> e.orderId() == 101L)` to verify exact business keys instead of only looking at the total count.

### Exercise 2 — Creating a Custom TestExecutionListener

Write an `AbstractTestExecutionListener` that logs before/after tests. Configure `@TestExecutionListeners(mergeMode=MERGE_WITH_DEFAULTS)`, ensuring `ApplicationEventsTestExecutionListener` still works. Try switching to replace mode (on a separate test) to observe the difference.

### Exercise 3 — Before and After Commit

Create an `@Transactional` service that publishes an event and an `@TransactionalEventListener(AFTER_COMMIT)` listener. Run the test in a rolled-back transaction and compare:

- Does `ApplicationEvents` record the published event?
- Does the after-commit listener execute?
- After a real commit, how does the outcome change?

Explain why a test asserting only `events.stream(...)` is insufficient to prove a transaction committed.

### Exercise 4 — Async Listener

Add an `@Async` listener with an observable outcome. Use a latch/Future to await completion, then assert the side effect. Keep assertions about **the event being published** separate from assertions about **the listener having handled it**.

### Exercise 5 — `@BeforeEach` and Test Instances

Write a `@BeforeEach` accepting `ApplicationEvents` and calling `clear()`. Add two tests publishing two different order IDs. Confirm both tests remain independent, even when Spring caches the same `ApplicationContext`.

## 13. Usage Principles and Common Mistakes

| Mistake | Problem | Correct Approach |
| --- | --- | --- |
| Adding `@RecordApplicationEvents` while dropping default `TestExecutionListeners` | No listener manages recording | Keep default listeners or register the required listener |
| Calling `new ApplicationEventsTestExecutionListener()` in a test | Does not integrate with `TestContextManager` | Use `SpringExtension` / TestContext |
| Trying to `@Autowired ApplicationEvents` into constructor | Dependency only exists in the test method lifecycle | Accept as parameter in test/`@BeforeEach`/`@AfterEach` |
| Using `events.stream().count()` to count domain events | Includes framework events or wrappers | Filter with `stream(MyEvent.class)` |
| Casting `PayloadApplicationEvent` to POJO | `ClassCastException` | Use typed stream to get payloads |
| Assuming `clear()` cancels publish/side effects | Only the recording is cleared; business logic already ran | Use clear only to mark an observation boundary |
| Assuming recorded event means listener finished | Async listener may still be running | Assert side effects and wait with a timeout |
| Assuming recorded event means DB committed | Event may be emitted in a rolled-back transaction | Test after-commit and real transactions |
| Accessing `ApplicationEvents` outside JUnit method lifecycle | Recording context does not exist yet | Use the proper lifecycle |
| Using event-recording listener to test out-of-JVM brokers | Cannot observe messages outside `ApplicationContext` | Use broker integration tests |
| Assuming all async events on pools are captured | Thread propagation is not guaranteed by default | Distinguish publisher thread from background executors |

**Remember:** `ApplicationEventsTestExecutionListener` is Spring TestContext infrastructure **registered by default** to support `@RecordApplicationEvents`; it lets you test which events an application **published** using `ApplicationEvents.stream(...)`. Obtain `ApplicationEvents` within each test's lifecycle, filter by domain event type, call `clear()` before an action when needed, and test commit/async side effects separately.

## Official Documentation

- Spring Framework — TestContext **Application Events**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework — `@RecordApplicationEvents`: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html
- Spring Framework 6.2 — `ApplicationEventsTestExecutionListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEventsTestExecutionListener.html
- Spring Framework 6.2 — `ApplicationEvents` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework — `TestExecutionListener` configuration: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html
- Spring Framework — Test Execution Events (distinguishing `EventPublishingTestExecutionListener`): https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/test-execution-events.html
