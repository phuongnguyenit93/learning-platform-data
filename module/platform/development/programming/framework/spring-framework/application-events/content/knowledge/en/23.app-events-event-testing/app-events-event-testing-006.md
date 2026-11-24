# Injecting ApplicationEvents into Tests to Test Spring Framework Application Events

## 1. The Problem: How to Confirm an Application Event Was Emitted?

In a Spring application, a service can publish an event via `ApplicationEventPublisher.publishEvent(...)` for `@EventListener` or `ApplicationListener` handlers to process. When writing tests, we usually want to verify **the right event type, right payload, and right emission count** without inventing a custom fake event bus or relying on reading console output.

For example, when accepting an order:

~~~java
public record OrderSubmitted(String orderId) {}

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void submit(String orderId) {
        // Perform business logic...
        publisher.publishEvent(new OrderSubmitted(orderId));
    }
}
~~~

This is an **integration illustration**, not a standalone program. A test may ask:

- Was `OrderSubmitted` actually published?
- Does it carry the right `orderId`?
- After a single submit command, was there **exactly one** `OrderSubmitted`, or was it emitted twice?
- If validation fails before publication, is any event still emitted?
- If a listener produces a follow-up event, is that follow-up event published and recorded?
- If a listener runs after commit, did the test actually commit?

Spring TestContext Framework provides a built-in solution: **`@RecordApplicationEvents` combined with `ApplicationEvents`** in the `spring-test` module. This tool records application events published to the `ApplicationContext` within **each test method's lifecycle**, then lets you query them via a `Stream`.

Core usage example:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@RecordApplicationEvents
class OrderServiceTest {

    @Autowired
    OrderService service;

    @Test
    void shouldPublishOrderSubmitted(ApplicationEvents events) {
        service.submit("ORD-257");

        long count = events.stream(OrderSubmitted.class).count();
        assertEquals(1L, count);
    }
}
~~~

This is a **sketch snippet** requiring `OrderTestConfig`, imports, and JUnit dependencies. A complete runnable example appears in section 6.

**Keep in mind right away:** `ApplicationEvents` in this article is **a test-only API in `org.springframework.test.context.event`**, not `ApplicationEventPublisher` used to publish events in production.

## 2. Participating Components

| Component | Package | Responsibility |
|---|---|---|
| `ApplicationEventPublisher` | `org.springframework.context` | Publishes an event/payload into the Spring context |
| `@EventListener` | `org.springframework.context.event` | Marks a method receiving an event type |
| `ApplicationEvents` | `org.springframework.test.context.event` | Queries events **recorded in the current test** |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Enables event recording for a test class |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Manages creating/registering the collector per test lifecycle |
| `SpringExtension` | `org.springframework.test.context.junit.jupiter` | Bridges Spring TestContext with JUnit Jupiter |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Combines `SpringExtension` and test context configuration |
| `@SpringBootTest` | `org.springframework.boot.test.context` | Starts a Spring Boot test context if the application uses Boot |

Event recording has existed in Spring Framework since **5.3.3**, so Spring Boot is not mandatory. In Spring Framework 6.2, you can use `spring-context`, `spring-test`, and JUnit Jupiter directly.

Relationship diagram:

~~~text
JUnit Jupiter @Test
    |
    +-- SpringExtension + Spring TestContext
    |       |
    |       +-- @RecordApplicationEvents
    |       +-- ApplicationEventsTestExecutionListener
    |               |
    |               +-- collector for the current test method
    |
    +-- call OrderService.submit("ORD-257")
    |       |
    |       +-- ApplicationEventPublisher.publishEvent(OrderSubmitted)
    |                  |
    |                  +-- ApplicationContext dispatches events
    |                  +-- @EventListener handlers process (per config)
    |                  +-- test collector records event
    |
    +-- assert events.stream(OrderSubmitted.class)
    |
    +-- end of test -> collector is not a global history
~~~

**Note:** the invocation order between production listeners and the test recording listener is not a business contract to rely on. When testing listener exceptions, async behavior, or transactions, verify the final state rather than assuming calling `publishEvent` means every listener succeeded.

## 3. Three Minimal Steps to Inject ApplicationEvents

### Step 1: Integrate with Spring TestContext

With JUnit Jupiter, use:

~~~java
@SpringJUnitConfig(classes = MyConfig.class)
class MyTest {
    // ...
}
~~~

`@SpringJUnitConfig` is a convenience annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. In a Spring Boot application, `@SpringBootTest` can create the context, yet **`@RecordApplicationEvents` is still an annotation from `spring-test`**, not a Boot-invented event-recording mechanism.

### Step 2: Enable Recording on the Test Class

~~~java
@RecordApplicationEvents
@SpringJUnitConfig(classes = MyConfig.class)
class MyTest {
}
~~~

The **`@RecordApplicationEvents`** annotation applies at the **test class** level or as a meta-annotation. It tells Spring TestContext to record application events emitted during each test's execution.

`ApplicationEventsTestExecutionListener` is registered **by default** when using the default set of test listeners. If you declare `@TestExecutionListeners` replacing the entire list, you may accidentally drop this listener, causing recording not to work as expected.

### Step 3: Obtain ApplicationEvents in the Test

**Recommended approach with JUnit Jupiter: parameter injection**

~~~java
@Test
void capturesEvent(ApplicationEvents events) {
    // events exists within the scope of the running test method.
}
~~~

Spring also supports parameters on `@BeforeEach` and `@AfterEach`:

~~~java
@BeforeEach
void resetEvents(ApplicationEvents events) {
    events.clear();
}
~~~

**Alternative approach: field injection**

~~~java
@Autowired
ApplicationEvents events;
~~~

Use a field when you want to reference the object from multiple test/lifecycle methods without repeating parameters, while understanding the data is managed per **test method execution**, not an accumulated store spanning the whole class.

**Do not inject into the test class constructor:**

~~~java
// Do not do this: @RecordApplicationEvents does not guarantee
// ApplicationEvents is ready inside the test constructor.
class MyTest {
    MyTest(ApplicationEvents events) {
    }
}
~~~

This is an **intentional counterexample**. The Spring reference explicitly states `ApplicationEvents` is a *resolvable dependency* bound to the test method lifecycle, so it is inaccessible outside that scope and **cannot be `@Autowired` into a test class constructor**.

## 4. The ApplicationEvents API: stream, stream(Class), and clear

The core API resides at:

~~~java
import org.springframework.test.context.event.ApplicationEvents;
~~~

Three key methods:

| Method | Result | When to Use |
|---|---|---|
| `stream()` | `Stream<ApplicationEvent>` of all recorded events | Inspecting envelopes or filtering multiple Spring events |
| `stream(Class<T> type)` | `Stream<T>` of events **or payloads** of type `T` | Asserting business event types; use by default |
| `clear()` | Clears the current test's collector contents | Excluding setup events or separating assertion phases within one test |

Example:

~~~java
long submittedCount = events.stream(OrderSubmitted.class).count();

boolean includesOrder = events.stream(OrderSubmitted.class)
    .anyMatch(e -> e.orderId().equals("ORD-257"));

List<String> ids = events.stream(OrderSubmitted.class)
    .map(OrderSubmitted::orderId)
    .toList();

events.clear();
~~~

These are integration snippets: they require the `OrderSubmitted` record, an `events` variable, and `java.util.List`. A Java `Stream` is **single-use**; after calling a terminal operation such as `count()`, if you want to query again, **call `events.stream(...)` again** rather than reusing a consumed stream.

### Why Does stream(Class) Still Work with POJO Payloads?

Spring allows `publishEvent(Object)` to accept an object **that does not extend `ApplicationEvent`**, such as a Java record:

~~~java
public record OrderSubmitted(String orderId) {}

publisher.publishEvent(new OrderSubmitted("ORD-257"));
~~~

Spring can wrap this object in `PayloadApplicationEvent` for delivery through the system. `ApplicationEvents.stream(OrderSubmitted.class)` still returns **`OrderSubmitted` payloads**, sparing the test author from casting the envelope.

If you need to inspect `PayloadApplicationEvent` itself:

~~~java
events.stream()
    .filter(e -> e instanceof PayloadApplicationEvent<?>)
    .forEach(e -> {
        // Inspect the envelope only when truly needed.
    });
~~~

This is **illustrative code** with `import org.springframework.context.PayloadApplicationEvent`. In most business tests, inspecting typed payloads makes code clearer and less coupled to envelope internals.

### What Does clear() Not Do?

`events.clear()` only **clears the observed history in the test collector**. It does **not**:

- Cancel an already published event.
- Reverse side effects of `@EventListener`.
- Roll back a transaction.
- Remove messages from a broker.
- Cancel running async work.
- Reset singleton bean or database state.

If a test needs to control business state, reset repositories/mocks/fixtures separately. `clear()` only helps distinguish events recorded before or after a milestone in the test.

## 5. Why Should Each Test Use Its Own Collector?

Spring can **cache the ApplicationContext** so multiple tests reuse the same context, yet `ApplicationEvents` is not meant to be a log accumulating from context creation until JVM shutdown. Spring TestContext manages it per **single test method** lifecycle.

Benefits:

- Prevents test A from needing to know how many events preceding test B emitted.
- Allows testing multiple business flows with independent assertions.
- When using a method parameter, readers see the collector belongs to the current test.
- Avoids registering a global listener manually and tearing it down after every test.

However, understand that "the same test" does not mean "only events emitted by the single service line under test." `@BeforeEach`, helpers, setup methods, or TestContext listeners may publish events while the test runs.

**Safe practices:**

1. Filter by **business event type**, e.g., `OrderSubmitted.class`.
2. Call `events.clear()` in `@BeforeEach` if setup events should be discarded.
3. In multi-step tests, call `clear()` between steps when asserting each stage independently.
4. Do not assert the count of **all** events via `events.stream().count()` unless you truly control every event in the context.
5. Do not depend on test method execution order to obtain an expected event list.

## 6. Complete Runnable Example: Java 17, Spring Framework 6.2, and JUnit Jupiter

This example uses:

- Java **17+**, Maven.
- `spring-context` and `spring-test` version **6.2.8**.
- JUnit Jupiter **5.12.2**, Maven Surefire **3.5.3**.
- No Spring Boot, database, web server, or message broker required.

The small application exhibits three behaviors:

1. `OrderService.submit(...)` validates the ID and emits `OrderSubmitted`.
2. `OrderFollowUpListener` receives `OrderSubmitted` and returns an `OrderAcknowledged`; Spring publishes this follow-up event via the synchronous listener return-value mechanism.
3. Tests inject `ApplicationEvents` to prove both **the original event and the follow-up event** appeared; other tests prove `clear()` and the validation branch emitting no events.

### Project Structure

~~~text
application-events-test/
├── pom.xml
└── src/test/java/demo/ApplicationEventsInjectionTest.java
~~~

There is no production code outside `src/test` because the example intentionally presents a minimal setup for event testing. In a real project, move services/events to `src/main/java` and keep tests in `src/test/java`.

### pom.xml

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
            <version>5.12.2</version>
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
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/test/java/demo/ApplicationEventsInjectionTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ApplicationEventsInjectionTest.Config.class)
@RecordApplicationEvents
class ApplicationEventsInjectionTest {

    @Autowired
    OrderService service;

    // Option 1: field injection, also supported by Spring TestContext.
    @Autowired
    ApplicationEvents fieldEvents;

    // Option 2: lifecycle parameter injection.
    @BeforeEach
    void resetRecordedEvents(ApplicationEvents events) {
        events.clear();
    }

    @Test
    void methodParameterReceivesPayloadAndFollowUp(ApplicationEvents events) {
        service.submit("ORD-257");

        assertEquals(1L, events.stream(OrderSubmitted.class).count());
        assertEquals(
            List.of("ORD-257"),
            events.stream(OrderSubmitted.class)
                .map(OrderSubmitted::orderId)
                .toList()
        );

        // Second event returned by a synchronous @EventListener.
        assertEquals(1L, events.stream(OrderAcknowledged.class).count());
        OrderAcknowledged ack = events.stream(OrderAcknowledged.class)
            .findFirst()
            .orElseThrow();
        assertEquals("ORD-257", ack.orderId());
        assertEquals("ACCEPTED", ack.status());
    }

    @Test
    void autowiredFieldCanBeUsedAndCleared() {
        service.submit("ORD-258");

        assertTrue(
            fieldEvents.stream(OrderSubmitted.class)
                .anyMatch(e -> e.orderId().equals("ORD-258"))
        );
        assertEquals(1L, fieldEvents.stream(OrderAcknowledged.class).count());

        fieldEvents.clear();
        assertEquals(0L, fieldEvents.stream(OrderSubmitted.class).count());
        assertEquals(0L, fieldEvents.stream(OrderAcknowledged.class).count());
    }

    @Test
    void rejectedCommandPublishesNoOrderEvent(ApplicationEvents events) {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.submit(" ")
        );

        assertEquals(0L, events.stream(OrderSubmitted.class).count());
        assertEquals(0L, events.stream(OrderAcknowledged.class).count());
    }

    public record OrderSubmitted(String orderId) {
    }

    public record OrderAcknowledged(String orderId, String status) {
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is blank");
            }
            publisher.publishEvent(new OrderSubmitted(orderId));
        }
    }

    public static final class OrderFollowUpListener {
        @EventListener
        public OrderAcknowledged acknowledge(OrderSubmitted event) {
            return new OrderAcknowledged(event.orderId(), "ACCEPTED");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderFollowUpListener orderFollowUpListener() {
            return new OrderFollowUpListener();
        }
    }
}
~~~

### Run and Verify

From the `application-events-test` directory:

~~~bash
mvn test
~~~

Once dependencies are downloaded and tests succeed, check the two key lines in the Maven Surefire report:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

These are the **two core outcome lines to expect**, without guaranteeing identical full Maven logs across environments. Detailed test reports reside under `target/surefire-reports/` after execution.

### Why Is This Test Suite Meaningful?

**Test 1 — parameter injection:**

- `SpringExtension` supplies `ApplicationEvents` to **the test method itself**.
- `OrderService.submit("ORD-257")` publishes an `OrderSubmitted` payload.
- `OrderFollowUpListener` receives the event and returns an `OrderAcknowledged`; Spring publishes the returned object.
- The collector records both event types. The test verifies **both counts and contents**.

**Test 2 — field injection and clear:**

- `@Autowired ApplicationEvents fieldEvents` demonstrates the alternative usage.
- The test verifies the event with ID `ORD-258`, then calls `fieldEvents.clear()`.
- After `clear()`, the test collection holds no events. The fact that the service published or the listener ran **is not undone**.

**Test 3 — failure branch before publish:**

- `service.submit(" ")` fails validation and throws an exception **before calling the publisher**.
- The test confirms neither `OrderSubmitted` nor `OrderAcknowledged` was produced.
- This is a stable negative test, unaffected by whether an exception in a listener would make a collector miss events.

The three test methods are independent; they do not rely on test class execution order. `@BeforeEach` clears the collector so assertions stay meaningful even if setup or the framework emits unrelated events.

## 7. Distinguishing "Event Was Published" from "Listener Actually Succeeded"

One of the most dangerous misconceptions is:

> "`events.stream(OrderSubmitted.class).count() == 1` so the listener succeeded."

Incorrect. `ApplicationEvents` records events **published** and observed in TestContext, not a durable per-listener completion ledger.

For example:

~~~java
@EventListener
public void handle(OrderSubmitted event) {
    emailGateway.send(event.orderId()); // May throw or time out.
}
~~~

Asserting only that `OrderSubmitted` appeared does not prove an email was sent, an external system received it, or the listener completed successfully.

There are three distinct testing layers:

| Layer to Prove | Appropriate Assertion |
|---|---|
| Service emits the right event | `ApplicationEvents.stream(EventType.class)`, payload, and count |
| Listener is invoked properly | Spy/fake collaborator, test-managed counter, or follow-up event emitted only when listener handles it |
| Business effect completed | Inspect DB/query/fake API/outbox state or actual acknowledgment |

Section 6's `OrderAcknowledged` test generates a follow-up event from the listener **after the method returns**. That provides extra evidence the listener reached its return point along the default synchronous path. Still, it does not guarantee a side effect outside the JVM was durably saved unless asserted separately.

A good integration test can combine the recorder with a fake collaborator—for example verifying the call count on an email adapter and inspecting events independently. Do not replace every mock or integration assertion with `ApplicationEvents` alone.

## 8. Field Injection, Method Injection, and Constructor Injection

Clear comparison to avoid misusing the test API:

| Location | Valid? | Notes |
|---|---|---|
| `@Test` parameter | **Yes — recommended** | Collector is bound to the current method |
| `@BeforeEach` parameter | **Yes** | Handy for `clear()` after setup |
| `@AfterEach` parameter | **Yes** | Handy for asserting events at the end of a test |
| `@Autowired ApplicationEvents` field | **Yes** | Resolved by TestContext per method scope |
| Test class constructor | **No** | Test-scoped dependency is unavailable at test instance creation time |
| Production singleton bean constructor | **Do not use** | `ApplicationEvents` is a test-only API, not a production dependency |
| `@BeforeAll`/`@AfterAll` | **Do not rely on** | Outside the lifecycle of **a single test method** |
| Tests without Spring TestContext | **Not available automatically** | Plain JUnit/Mockito unit tests need a different strategy |

In Java/JUnit Jupiter, parameter injection syntax is concise:

~~~java
@Test
void createsEvent(ApplicationEvents events) {
    service.submit("ORD-257");
    assertEquals(1L, events.stream(OrderSubmitted.class).count());
}
~~~

Choose field injection when a test has multiple helper/lifecycle methods needing access to the current collector, but never store this field in a static variable or use it after the test completes.

### Why Should Static ApplicationEvents Never Be Used?

The collector is not a singleton event store. Grabbing an instance and storing it in a static field or passing it to threads outliving the test can cause assertions to read the wrong lifecycle, leak data between tests, or hold an invalid collector. Keep access within test methods and appropriate synchronous helpers.

## 9. Customizing TestExecutionListeners Without Losing Recording

`ApplicationEventsTestExecutionListener` is included by default in TestContext's standard listener set. However, this configuration can accidentally lose it:

~~~java
@TestExecutionListeners(MySpecialListener.class)
@SpringJUnitConfig(classes = MyConfig.class)
@RecordApplicationEvents
class CustomTest {
}
~~~

This is **risk-illustration code**: if the new configuration replaces the default list without registering `ApplicationEventsTestExecutionListener`, event recording may stop working.

One way to preserve default listeners is **merging**:

~~~java
@TestExecutionListeners(
    listeners = MySpecialListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
@RecordApplicationEvents
@SpringJUnitConfig(classes = MyConfig.class)
class CustomTest {
}
~~~

This is a **configuration snippet** requiring application-defined `MySpecialListener` and `MyConfig`, plus `TestExecutionListeners`/JUnit imports. Do not add it to section 6's runnable example if no custom execution listener is needed.

Another option is listing the full set manually including `ApplicationEventsTestExecutionListener`, yet that risks omitting other listeners such as dependency injection, transactions, or test context setup. For most projects, **keeping defaults** is simplest and safest.

### ApplicationEventsTestExecutionListener Differs from EventPublishingTestExecutionListener

Two types are easily confused due to similar names:

- `ApplicationEventsTestExecutionListener` manages **recorded ApplicationEvents** for the current test.
- `EventPublishingTestExecutionListener` publishes **TestContext lifecycle events** such as `BeforeTestMethodEvent` and `AfterTestMethodEvent` so other Spring beans can observe them.

A listener emitting test lifecycle events **does not replace** the recorder; the two components perform different jobs. When using the general `events.stream()`, you may see framework events alongside business events, so filter by specific class in assertions.

## 10. Testing Event Content: Do Not Just Count

A weak test:

~~~java
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

It proves there is one event of type `OrderSubmitted`, yet the event could have the wrong `orderId`, miss `version`, or target the wrong tenant.

A better test:

~~~java
List<OrderSubmitted> submitted =
    events.stream(OrderSubmitted.class).toList();

assertEquals(1, submitted.size());
assertEquals("ORD-257", submitted.get(0).orderId());
~~~

This is an integration snippet; it requires `java.util.List` and JUnit Jupiter assertions.

For events with multiple fields, add assertions on:

- **Aggregate ID**: which entity changed?
- **Event ID**: which publication attempt, stable across retries?
- **Version**: which snapshot of the aggregate, not stale?
- **Occurred-at timestamp**: valid/within an acceptable range? Avoid asserting an exact instant if generated by a runtime clock.
- **Correlation/causation ID**: preserves relationship to the command or parent event?
- **Tenant ID**: preserves the exact isolation boundary?
- **Business fields**: amounts, statuses, action types, not identifiers alone.

Do not dump full PII or secrets into test output for debugging. When comparing complex payloads, AssertJ recursive comparisons or JSON schema checks can help, while keeping assertions aligned with the event contract rather than every internal detail.

### Mutable Events Can Mislead Assertions

If an event payload holds a mutable entity:

~~~java
OrderEntity order = ...;
publisher.publishEvent(new OrderChanged(order));
order.setStatus("PAID");
~~~

In this example, the record/event may hold **the same OrderEntity reference**, so later the collector sees the mutated status even though the status differed at publication time. Hence, to test values **at the moment the event was emitted**, use proper immutable/snapshot payloads. `ApplicationEvents` does not automatically deep-copy every published object.

## 11. Transactions: A Recorded Event Does Not Mean Committed

A test can observe:

~~~java
long published = events.stream(OrderPlaced.class).count();
~~~

and still not know:

- Did transaction T1 **commit**?
- Did an error cause T1 to **roll back** after emitting the event?
- Did `@TransactionalEventListener(AFTER_COMMIT)` run?
- Was a broker/outbox message durably sent?

Distinguish **publication** from **transaction completion**.

### Common Trap: `@Transactional` Test Methods

In Spring Test, a test method marked `@Transactional` typically runs in a TestContext-managed transaction and **rolls back at the end of the test**. If the service emits an event inside that transaction, `ApplicationEvents` can still record the publication, while a listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    notification.send(event.orderId());
}
~~~

**does not run when the test transaction rolls back**, because no commit succeeded. An assertion checking only that `OrderPlaced` was published does not prove the `AFTER_COMMIT` listener ran.

When you want to test true post-commit behavior, pick one of two approaches:

1. Do not mark the test method itself transactional; call an `@Transactional` Spring service and let the service method finish/commit before assertions.
2. Inside a transactional test, use `TestTransaction` to intentionally conclude the transaction:

~~~java
@Test
@Transactional
void afterCommitShouldRun(ApplicationEvents events) {
    orderService.createOrder("ORD-257");

    assertEquals(1L, events.stream(OrderPlaced.class).count());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Here you can assert the AFTER_COMMIT callback outcome
    // via a fake adapter, separate repository, or corresponding follow-up event.
}
~~~

This is an **integration snippet**, not part of section 6's Maven demo: it requires `spring-tx`, a transaction manager, a persistence layer, `OrderPlaced`, `orderService`, Spring Test transaction setup, and `import org.springframework.test.context.transaction.TestTransaction`. Do not call `TestTransaction` without an active test transaction.

**Next boundary:** even if a listener ran `AFTER_COMMIT`, post-commit side effects can still fail without rolling back T1. If durability is required, an outbox/queue/idempotency design and tests of that durable state are needed.

### Reactive Transactions

With R2DBC and `ReactiveTransactionManager`, transaction state lives in the Reactor Context. Starting with Spring Framework 6.1+, reactive transactional event listeners need events carrying `TransactionContext` in their source, typically via `TransactionalEventPublisher`. `ApplicationEvents` only records events visible to the test collector; it **does not create reactive transactions**, subscribe to publishers, or force a constructed `Mono` to execute.

In reactive tests, **subscribe** (e.g., via `StepVerifier`) and only then assert recorded events and transaction outcomes along the true execution path. Do not confuse test `ApplicationEvents` with the application's reactive `TransactionContext`.

## 12. Async Listeners and Other Threads: How to Test?

An `@Async @EventListener` can run on an executor worker while the test thread continues. Thus the following code can **race**:

~~~java
service.submit("ORD-257");
assertEquals(1L, events.stream(FollowUpCompleted.class).count());
~~~

If `FollowUpCompleted` is emitted from an async worker, that event might not exist yet when the assertion runs. Two issues must be solved:

1. **Completion:** wait for async work with an explicit completion signal rather than `Thread.sleep(...)` with a guessed duration.
2. **Recording scope:** `@RecordApplicationEvents` manages the collector per test and supports events from the test thread and child threads under its current contract, yet **it does not guarantee every pre-existing/reused thread-pool thread or task finishing after the test receives the right collector**. Verify your executor's actual context/ThreadLocal propagation mechanism.

Simple example measuring listener execution via a collaborator:

~~~java
CountDownLatch done = new CountDownLatch(1);

@EventListener
public void on(OrderSubmitted event) {
    try {
        process(event);
    } finally {
        done.countDown();
    }
}

// Inside test:
service.submit("ORD-257");
assertTrue(done.await(3, TimeUnit.SECONDS));
~~~

This is **illustrative code** requiring a `done` field in a Spring-managed test collaborator, `CountDownLatch`/`TimeUnit` imports, and a real `process` method. If `@Async` is enabled, manage a dedicated executor and `@EnableAsync` configuration. Do not copy this into the synchronous demo without adding the bean, test state, and imports.

If the goal is asserting **a new event published from a thread pool**, not merely that the task completed, use a measurement mechanism able to observe the right thread/correlation. You can use a fake collaborator/spy to test async logic, an integration test with an appropriate executor, or configure context propagation directly. Do not assume calling `events.stream(FollowUpCompleted.class)` will always see events from any arbitrary thread regardless of timing and collector boundaries.

### When an `@Async` Listener Throws an Exception

Exceptions in an async worker usually do not propagate back to the publishing thread; tests must observe futures/handlers or state recorded by the worker. Do not assert only that `OrderSubmitted` was published and conclude the listener finished successfully. When post-commit work must run durably, `@Async` and recorder tests still do not replace an outbox/broker.

## 13. Testing Event Chaining and Collection Fan-Out

Spring allows an `@EventListener` method to **return an object** to publish a subsequent event. If it returns a `Collection` or array, each element is published as a separate event in a synchronous listener.

Example:

~~~java
@EventListener
public List<NotificationRequested> on(OrderSubmitted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

This is an integration snippet; `NotificationRequested` must be defined and the listener must be a Spring bean. With `ApplicationEvents`, you can assert:

~~~java
List<String> channels = events.stream(NotificationRequested.class)
    .map(NotificationRequested::channel)
    .toList();

assertEquals(List.of("EMAIL", "DASHBOARD"), channels);
~~~

With the default synchronous dispatcher, for a single fan-out listener and an ordered `List`, child event order normally follows list iteration order. However, do not treat this order as an end-to-end contract when executors, async, and multiple nodes are involved. When ordering is not required, checking value sets and counts is sturdier.

**Important distinction:** an `@EventListener` **returning a List** produces per-element publications; calling `publisher.publishEvent(list)` directly publishes **a single payload object of type List**, not multiple child events. Testing with `ApplicationEvents` catches this design mistake because `stream(NotificationRequested.class)` will contain none of the individual items.

## 14. Spring Boot Integration Tests and ApplicationEvents

If a project uses Spring Boot, the test syntax is usually concise:

~~~java
@SpringBootTest
@RecordApplicationEvents
class CheckoutEventsTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void emitsCheckoutCompleted(ApplicationEvents events) {
        events.clear();

        checkoutService.completeCheckout("CHK-257");

        assertEquals(
            1L,
            events.stream(CheckoutCompleted.class).count()
        );
    }
}
~~~

This is an **integration pattern**, not a standalone runnable program. `CheckoutService` and `CheckoutCompleted` are application-defined types. `@SpringBootTest` is imported from Spring Boot Test, whereas `ApplicationEvents` and `@RecordApplicationEvents` still come from Spring Framework TestContext.

Add appropriate test dependencies, usually `spring-boot-starter-test` with Boot dependency management; Spring Framework, JUnit, and compatible dependencies should be managed within the same stack version. Do not arbitrarily mix Spring 7.x with a Spring Boot starter built for another generation.

Key differences:

| Plain Spring Framework | Spring Boot |
|---|---|
| `@SpringJUnitConfig(Config.class)` | `@SpringBootTest` (or an appropriate test slice) |
| `spring-test` and JUnit Jupiter | Boot test starter integrating Spring TestContext |
| `@RecordApplicationEvents` | **Keep this exact annotation** |
| `ApplicationEvents` parameter/field | **Keep this exact API** |
| Minimal `@Bean` configuration | Can load real application configuration, though slower to start |

Do not use `@SpringBootTest` when you only need to verify one service emitting events and can build a small context with `@SpringJUnitConfig`; small tests run faster, have fewer dependencies, and are easier to analyze.

## 15. Sometimes No Spring Context Is Needed: Unit Testing with a Fake Publisher

`ApplicationEvents` fits when you want to verify **publication inside a real Spring ApplicationContext** and how TestContext records events. Yet if the goal is only testing whether a service calls `ApplicationEventPublisher.publishEvent(...)` with the right payload, a pure Java unit test can be faster:

~~~java
List<Object> emitted = new ArrayList<>();

ApplicationEventPublisher fakePublisher = emitted::add;

OrderService service = new OrderService(fakePublisher);
service.submit("ORD-257");

assertEquals(1, emitted.size());
assertEquals(
    new OrderSubmitted("ORD-257"),
    emitted.get(0)
);
~~~

This is an illustrative snippet (requiring `OrderService` constructor, `OrderSubmitted` record, `List`, `ArrayList`, assertions). Neither `@RecordApplicationEvents` nor `SpringExtension` is needed because there is no Spring TestContext. However, it **does not test `@EventListener` dispatch**, nor does it simulate listener ordering or transaction phases.

Choose tools by goal:

- **Unit test:** verify event emission logic and payload inside one service using a fake/Mockito.
- **Spring integration test:** verify beans, wiring, event publication, and return-value chaining via `ApplicationEvents`.
- **Transaction integration test:** verify publishing under commit/rollback, side effects, and a real database.
- **System test:** verify durable delivery via outbox/broker, retries, and idempotency.

The more boundaries involved, the less you can rely on a single `events.stream(...).count()`.

## 16. Common Errors When Injecting ApplicationEvents

| Symptom | Possible Cause | Fix |
|---|---|---|
| `ApplicationEvents` cannot be injected | Missing `@RecordApplicationEvents` or not using Spring TestContext | Add annotation + `@SpringJUnitConfig`/`@SpringBootTest` |
| `@RecordApplicationEvents` present yet collector does nothing | Custom `@TestExecutionListeners` dropped default listeners | Merge defaults or register `ApplicationEventsTestExecutionListener` |
| Injecting into test constructor fails | Dependency exists per test method, not constructor | Use a parameter on `@Test`/`@BeforeEach`/`@AfterEach` |
| `stream(OrderSubmitted.class)` is empty | Service did not emit, wrong event type/context, or occurred before test lifecycle | Check publisher, type, bean, and timing |
| `stream()` has more events than expected | Framework/test setup emitted extra events | Filter `stream(EventType.class)`, call `clear()` when appropriate |
| Duplicate events | Service emitted multiple times or a listener created same-type child events | Assert payload/eventId and exact count, not just boolean |
| Test A affected by state from B | Shared DB/singleton/queue state rather than the recorder | Reset dependencies/fixtures, not just calling `clear()` |
| Post-commit test sees no listener execution | `@Transactional` test rolls back by default | Commit explicitly or call the transactional service outside a test transaction |
| `@Async` makes assertions flaky | Worker not awaited or context did not follow thread | Latch/await and verify propagation/collector behavior |
| Stream throws `IllegalStateException` closed | Reusing a Java Stream after a terminal operation | Call `events.stream(...)` again |
| Event published yet listener failed | Recorder is not a completion/side-effect report | Assert collaborator/DB/outbox separately |
| Event payload in collector changed value | Payload holds a shared mutable object reference | Use immutable/snapshot events |
| Test misses events from another method | Collector is per method, not JVM-wide | Design assertions within the current test |
| Plain Mockito test lacks `ApplicationEvents` | No TestContext infrastructure | Use a fake publisher or integrate Spring TestContext |

## 17. Test Quality Checklist

An event-recording test meets quality standards when:

1. Proper Spring TestContext integration is used (`SpringExtension`, `@SpringJUnitConfig`, or Boot test).
2. `@RecordApplicationEvents` is on the class or applied via a composed annotation.
3. Default `TestExecutionListener`s remain intact or are merged properly.
4. `ApplicationEvents` is injected cleanly within method scope, preferring parameter injection.
5. Results are filtered by **business** event using `stream(Class)`.
6. Counts, IDs, and key fields are verified, not merely "event exists."
7. Publication assertions are separated from listener side-effect and transaction outcome assertions.
8. Negative tests exist (no success event emitted when conditions are unmet).
9. Tests do not depend on execution order, logs, or arbitrary sleeps.
10. When async, completion signals exist and thread/collector boundaries are understood.
11. When testing `AFTER_COMMIT`, the test transaction actually committed before assertions.
12. Test-only `ApplicationEvents` is never placed into production beans or static references.
13. `clear()` is never treated as a rollback or context reset operation.
14. A data-reset strategy exists outside the collector if contexts/tests share resources.
15. Tests are repeatable locally and in CI without depending on data from prior runs.

## 18. Review Questions

**1. How does ApplicationEvents differ from ApplicationEventPublisher?** `ApplicationEventPublisher` publishes events in the application; `spring-test`'s `ApplicationEvents` lets tests query recorded events.

**2. Is Spring Boot required?** No. `@RecordApplicationEvents` belongs to Spring Framework TestContext and works with `@SpringJUnitConfig`.

**3. Can ApplicationEvents be injected into a test class constructor?** No. It is bound to each test method's lifecycle; use a field or a test/lifecycle method parameter.

**4. Is calling just `events.stream().count()` enough?** Usually not, because other Spring/TestContext events exist. Use `events.stream(OrderSubmitted.class)` and inspect payloads.

**5. When calling `events.clear()`, do already sent events vanish from the system?** No. Only the collector's recorded event buffer is cleared.

**6. When a test method rolls back, does the recorder still see events emitted inside the transaction?** It can see that publication occurred; that does not prove the transaction committed or `AFTER_COMMIT` ran.

**7. Should async listener tests assert immediately after publish?** No. Wait for completion, handle exceptions, and verify the collector actually observes the emitting thread.

**8. Why is another event returned by `@EventListener` still recorded?** Spring publishes the returned object as a new event when a synchronous listener finishes normally, so the collector can observe the follow-up publication.

**9. Is `ApplicationEvents` a durable event store?** No. It is an event-recording utility for test scope, not for replaying across runs.

**10. When does a fake publisher make more sense?** When only testing that a service calls `publishEvent` with the right payload, without needing to verify Spring dispatch or transactions.

## 19. Summary

To **inject `ApplicationEvents` into Spring tests**, place `@RecordApplicationEvents` on the test class alongside `SpringExtension` (typically via `@SpringJUnitConfig` or `@SpringBootTest`), then receive `ApplicationEvents` via a **`@Test`/`@BeforeEach`/`@AfterEach` parameter** or an `@Autowired` field. Prefer method parameters because the collector is scoped to each individual test's lifecycle.

The `stream(EventType.class)` API verifies event type, emission count, and payload; `clear()` only erases recorded history inside the test. Distinguish an event **being published** from a listener **succeeding**, a transaction **committing**, or a message **being durably delivered**. For async and transactional listeners, explicitly verify completion or transaction phases rather than expecting the recorder to handle all of those semantics automatically.

### Official Documentation

- [Spring Framework 6.2 Reference — Application Events in TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html) — guide to `@RecordApplicationEvents`, method parameter/field injection, and constructor limits.
- [Spring Framework 6.2 Javadoc — ApplicationEvents](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html) — `stream()`, `stream(Class)`, and `clear()`.
- [Spring Framework 6.2 Javadoc — RecordApplicationEvents](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html) — lifecycle and recording scope.
- [Spring Framework 6.2 Javadoc — ApplicationEventsTestExecutionListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEventsTestExecutionListener.html) — collector registration in TestContext.
- [Spring Framework 6.2 Reference — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html) — annotation and composed annotations.
- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener`, `AFTER_COMMIT`, and rollback.
- [Spring Framework 6.2 Reference — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html) — limitations with shared test state.
