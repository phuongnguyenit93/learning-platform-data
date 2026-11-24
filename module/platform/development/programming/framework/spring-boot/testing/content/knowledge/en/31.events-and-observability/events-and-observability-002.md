# Verifying Event Type, Payload, and Publication Count in Spring Boot

In Spring Boot, a service may call `ApplicationEventPublisher.publishEvent(...)` to signal that an **order was placed**, an **order was cancelled**, or **data changed**. Listeners using `@EventListener` or `@TransactionalEventListener` process the event—for example, writing an audit log, updating a projection, or sending a notification. A test that merely confirms “calling the place-order method does not throw an exception” **does not prove** that the event was published with the **right type, right data, and exact single occurrence**.

A reliable test must distinguish at least three questions:

1. **What event was published?** Is it the exact **class/type**, or a different type that happens to have similar fields?
2. **Is the payload accurate?** `orderId`, `quantity`, `correlationId`, and other business fields must be exact, not merely `notNull`.
3. **How many times was it published?** One operation emits exactly one event, neither missing nor duplicated; multiple operations are counted accurately, and each type is counted separately.

Add two extended observability questions: did the listener **handle** the event the right number of times, and did an external side effect (email, Kafka message, database row) **complete**? **Publish ≠ listener execution ≠ external delivery.** These are different kinds of evidence and require different tests.

This lesson belongs to **Events and Observability** in **Spring Boot - testing**. It covers Spring's event mechanism, `@RecordApplicationEvents` and `ApplicationEvents`, filtering by type, verifying payload and count, Mockito `ArgumentCaptor` for unit tests, the difference between publishing and handling, transaction commit/rollback, async listeners, common pitfalls, and a **Java 17 + Spring Boot 3.5 + JUnit Jupiter** project with **17 test methods**. The code uses Spring application events **within the same JVM**, requiring no Docker, database, or event broker.

## 1. What Is an Application Event and Where Does It Go?

Spring's ApplicationContext includes an event publisher. When code invokes:

```java
publisher.publishEvent(
        new OrderPlacedEvent("ORD-1", 2, "REQ-1"));
```

Spring's multicaster dispatches the event to compatible `ApplicationListener` or `@EventListener` targets. Custom events **do not have to extend `ApplicationEvent`**: a record like `OrderPlacedEvent` can act as the payload object. Spring wraps that object in `PayloadApplicationEvent` to pass it through the internal event listener infrastructure.

```text
CheckoutService.placeOrder(...)
            |
            +-- validate order ID / quantity / correlation ID
            |
            +-- ApplicationEventPublisher.publishEvent(OrderPlacedEvent)
                         |
                         v
             ApplicationEventMulticaster
                         |
             +-----------+----------------+
             |                            |
             v                            v
      @EventListener                Spring TestContext
      OrderEventObserver            @RecordApplicationEvents
             |                            |
             v                            v
      process / update              ApplicationEvents.stream(
      listener state                OrderPlacedEvent.class)
             |                            |
             v                            v
      assert listener count         assert publish count,
      and listener payload          type, payload
```

**Key rules:**

- `ApplicationEventPublisher.publishEvent(Object)` is Spring's **in-process** mechanism; by itself it **does not send to Kafka/RabbitMQ** and provides no durable delivery guarantee.
- Under typical Spring configuration, `@EventListener` methods are called **synchronously** by the default multicaster; however, an application can configure executors, async listeners, transaction-bound listeners, or a different multicaster. Tests must account for the actual configuration.
- `@EventListener` can consume a **payload record** directly, e.g., `void onPlaced(OrderPlacedEvent event)`.
- `@EventListener` can be **conditional** or accept only a subtype. A listener not being called does not mean the publisher never published.
- If a listener method returns an object instead of `void`, Spring can **publish a follow-up event from the return value**. This is an additional emission source to account for when counting.
- An event does not mean a transaction has committed. With `@TransactionalEventListener`, a listener can wait for commit/rollback; meanwhile `@RecordApplicationEvents` records that the event **was published**, without guaranteeing the transaction succeeded.
- A single request can emit multiple event types; **do not use the total count of all Spring events** as the business event count because Spring Framework also emits context/lifecycle/test events.

### Why Are Record Events Great for Payload Testing?

Suppose:

```java
public record OrderPlacedEvent(
        String orderId,
        int quantity,
        String correlationId) {
}
```

A Java 17 record automatically provides `equals`, `hashCode`, and accessors `orderId()`/`quantity()`/`correlationId()`. This allows tests to compare the entire payload:

```java
assertThat(published)
        .containsExactly(
            new OrderPlacedEvent("ORD-1", 2, "REQ-1"));
```

If an event is constructed with the wrong quantity or correlation ID, the assertion fails. For mutable classes or payloads containing timestamps/random IDs, inject a `Clock`/ID generator for deterministic tests or use field-by-field assertions rather than exact wall-clock comparisons. Do not add dynamic timestamps to events just to look realistic if it makes tests flaky.

## 2. `@RecordApplicationEvents` and `ApplicationEvents`

Spring TestContext provides the `@RecordApplicationEvents` annotation (since Spring Framework 5.3.3) to collect application events **published within the scope of each test method**. Typical usage in JUnit Jupiter:

```java
@SpringBootTest
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    CheckoutService service;

    @Test
    void publishesExactlyOnce(ApplicationEvents events) {
        service.placeOrder("ORD-1", 2, "REQ-1");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
    }
}
```

This is an illustrative snippet requiring classes/imports and a Spring context; the complete project is in Section 6. Spring TestContext must include `ApplicationEventsTestExecutionListener`; this listener is registered **by default**, unless your custom `@TestExecutionListeners` drops the defaults.

### Core API

| API | Meaning | Testing Notes |
|---|---|---|
| `@RecordApplicationEvents` | Enables event recording for the test class | Do not place on a single method instead of the class |
| `ApplicationEvents events` | Logical snapshot/stream of events in the current test | Inject into a JUnit method or field |
| `events.stream()` | Streams **every `ApplicationEvent` recorded** | May include Spring context/test/lifecycle events |
| **`events.stream(OrderPlacedEvent.class)`** | Streams events **or payloads** of this type | Returns `Stream<OrderPlacedEvent>` when the event is a POJO/record payload |
| `events.stream(...).count()` | Number of events/payloads of the specified type | Use `1L`, `2L`, `0L` explicitly |
| `events.stream(...).toList()` | Gets a snapshot list to assert type/content/order | Streams are one-shot; create a new stream each time |
| `events.clear()` | Clears current **recorded events** for the test | Does not undo publication or reset listener side effects |
| `@BeforeEach void reset(ApplicationEvents events)` | Resets the test baseline when needed | Per-test scope; does not clear a global bus |

**Common pitfall:** a record event is usually dispatched by Spring via `PayloadApplicationEvent`. Hence `events.stream()` returns `ApplicationEvent` objects (exposing the wrapper), whereas `events.stream(OrderPlacedEvent.class)` **filters and unwraps the strongly typed payload**. Do not cast `events.stream()` directly to `OrderPlacedEvent` or assert the wrapper type as a business event.

### Why Not Count `events.stream().count()`?

When running `@SpringBootTest`, the application context also publishes `ContextRefreshedEvent`, `ContextClosedEvent`, and other framework events; Spring TestContext can also publish test lifecycle events. The total event count depends on environment and initialization order. An assertion like:

```java
assertThat(events.stream().count()).isEqualTo(1);
```

is **too broad** when you only want to prove **one `OrderPlacedEvent`**. In real code, write:

```java
assertThat(events.stream(OrderPlacedEvent.class).count())
        .isEqualTo(1L);
```

If you need to count **all business event types** under a custom policy, define a marker interface/group of domain event types and filter meaningfully—do not equate all application events with a single domain event.

### What Does `ApplicationEvents.clear()` Do?

`clear()` only **removes events recorded so far in the current observation window**. It does not unpublish events from the publisher, cancel executed callbacks, unsend emails, or erase records saved by listeners. For tests needing a clean baseline, you can call both:

```java
@BeforeEach
void reset(ApplicationEvents events) {
    events.clear();      // reset test log
    observer.clear();    // reset fake listener state
}
```

This snippet assumes `observer` is a test bean or component with a `clear()` API. The complete example below uses this strategy. For parallel tests sharing a cached context, ensure observer state is isolated by test ID or avoid parallel execution; `events.clear()` alone does not make singleton listener state thread-safe or test-isolated.

## 3. Verifying Event Type: The Type Must Be Exact

Suppose a service has two event types:

```java
public record OrderPlacedEvent(
        String orderId, int quantity, String correlationId) {}

public record OrderCancelledEvent(
        String orderId, String reason, String correlationId) {}
```

When a test calls `placeOrder(...)`, it should assert:

- There is an **`OrderPlacedEvent`** of the exact type.
- There is **no `OrderCancelledEvent`**.
- The two types are not confused even though both contain `orderId` or share the `Order` prefix.
- If logic selects an event type conditionally, test each branch rather than only asserting `notNull`.

```java
List<OrderPlacedEvent> placed =
        events.stream(OrderPlacedEvent.class).toList();

assertThat(placed).containsExactly(
        new OrderPlacedEvent("ORD-1", 2, "REQ-1"));

assertThat(events.stream(OrderCancelledEvent.class).count())
        .isZero();
```

Here `events.stream(Class<T>)` enables type-safe filtering. Attempting to cast `PayloadApplicationEvent<?>` to the record checks the wrong abstraction layer and risks a `ClassCastException`.

### Type Identity Differs from Content

Avoid comparing like this:

```java
assertThat(events.stream().anyMatch(
        e -> e.toString().contains("ORD-1"))).isTrue();
```

This is an anti-pattern: a wrapper's or framework event's `toString()` could accidentally contain matching text, and message formatting can change. Extract the **exact type**, then assert **field values**. With Java records, `containsExactly(new OrderPlacedEvent(...))` simultaneously verifies type, count, order, and the full payload.

### An Event Type vs. a Concrete Subclass

`stream(MyType.class)` uses type-based filtering; if inheritance is used, subtypes match the requested supertype. When policy demands the event **must be the exact concrete class**, check `event.getClass().equals(MyEvent.class)` per event, or use records/final types. When policy allows subtypes, use `isInstanceOf`/filter by a base interface. Do not pick assertion styles arbitrarily: **“is assignable to this type”** differs from **“is this exact class with no subtypes”**.

## 4. Verifying Content: Avoid Weak or Brittle Assertions

A publish test should verify **business-meaningful fields**:

| Field | Why Check It? | Useful Assertion |
|---|---|---|
| `orderId` | Routing/dedup and entity identification | Matches exact ID from request |
| `quantity` | Catch events emitted with default or corrupted quantity | Matches expected integer |
| `correlationId` | Call-chain tracing, request reconciliation | Preserves ID from input |
| `event type` | Correct business workflow branch | `OrderPlacedEvent.class`, not cancelled |
| `reason` for cancel event | Correct business reason propagation | Exact string or appropriate enum |
| `timestamp` if present | Time of emission/recording | Inject `Clock.fixed(...)` or compare within tolerance |
| `aggregate version` if present | Ordering/optimistic concurrency | Assert version matches expected event value |
| `schemaVersion` if present | Broker compatibility | Assert contract value, not mere presence |

Concrete example:

```java
OrderPlacedEvent event =
        events.stream(OrderPlacedEvent.class)
                .findFirst()
                .orElseThrow();

assertThat(event.orderId()).isEqualTo("ORD-1");
assertThat(event.quantity()).isEqualTo(2);
assertThat(event.correlationId()).isEqualTo("REQ-1");
```

**Limitation:** `findFirst()` alone **does not prove uniqueness**; there could be three events and it would still return the first. Pair it with `count() == 1` or `containsExactly(...)` to verify the count.

Use fixed test values for IDs/timestamps (inject generators) when determinism is needed. Avoid asserting raw `toString()` output on events, unguaranteed JSON property ordering, or the current timezone when formatting is not what the test targets.

## 5. Counting Publications: Exactly Once, Multiple Times, None

### One Operation → One Event

```java
service.placeOrder("ORD-1", 2, "REQ-1");

assertThat(events.stream(OrderPlacedEvent.class).count())
        .isEqualTo(1L);
```

This is a direct assertion on the **publication count** of `OrderPlacedEvent` within the test scope, not the number of listeners invoked.

### Two Operations → Two Events

```java
service.placeOrder("ORD-1", 2, "REQ-1");
service.placeOrder("ORD-2", 3, "REQ-2");

assertThat(events.stream(OrderPlacedEvent.class).toList())
        .containsExactly(
            new OrderPlacedEvent("ORD-1", 2, "REQ-1"),
            new OrderPlacedEvent("ORD-2", 3, "REQ-2"));
```

With synchronous publishers and listeners, the order of two calls on the same thread is deterministic in this demo. In practice, with multiple threads/async dispatch, do not assume global ordering across event producers. If ordering is not part of the contract, use AssertJ `containsExactlyInAnyOrder(...)`; it still checks **completeness and no extras**.

### Invalid Input → No Publication

```java
assertThatThrownBy(
        () -> service.placeOrder("", 1, "REQ-1"))
        .isInstanceOf(IllegalArgumentException.class);

assertThat(events.stream(OrderPlacedEvent.class).count())
        .isZero();
```

This evidence matters when events should only be emitted **after validation/command acceptance**. If a service publishes first and throws afterward, the event may already have reached listeners. When DB transactions are involved, consider publication timing vs. commit and the business definition of the event.

### Why Count Each Type Separately?

If an action emits `OrderPlacedEvent`, a listener emits `AuditEvent`, and the framework emits context events, `events.stream().count() == 1` can fail even when the business publisher is completely right. Count explicitly:

```java
long placedCount =
        events.stream(OrderPlacedEvent.class).count();
long cancelledCount =
        events.stream(OrderCancelledEvent.class).count();

assertThat(placedCount).isEqualTo(1);
assertThat(cancelledCount).isZero();
```

If you need to assert that **no other domain event type** was published, cover the full domain taxonomy or use a marker interface/event registry; the two assertions above only exclude the types you explicitly checked.

## 6. Complete Maven Example: Java 17, Spring Boot 3.5, 17 JUnit Tests

The project models placing/cancelling orders and publishing two event types. `OrderEventObserver` receives events via `@EventListener`; tests separate **publish** evidence (via `@RecordApplicationEvents`) from **listener handled** evidence (via observer state). A second test class uses Mockito `ArgumentCaptor` to test only the publisher contract **at the unit level**.

### 6.1. Directory Tree

```text
order-events-testing/
├── pom.xml
└── src/
    ├── main/java/com/example/events/
    │   ├── EventsDemoApplication.java
    │   ├── OrderPlacedEvent.java
    │   ├── OrderCancelledEvent.java
    │   ├── CheckoutService.java
    │   └── OrderEventObserver.java
    └── test/java/com/example/events/
        ├── CheckoutEventIntegrationTest.java
        └── CheckoutServiceUnitTest.java
```

Tests require no `application.properties` or database. The Spring Boot application context loads `CheckoutService`, `OrderEventObserver`, and the default Spring event multicaster.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>order-events-testing</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` creates the Spring ApplicationContext and event infrastructure. `spring-boot-starter-test` provides Spring TestContext, JUnit Jupiter, AssertJ, and Mockito. `spring-boot-starter-web` is unnecessary since the example runs no controllers/HTTP. Java 17 supports records; the Spring Boot 3.5 parent manages dependency versions. Running `mvn test` executes both test classes.

### 6.3. Spring Boot Application Class

File **`src/main/java/com/example/events/EventsDemoApplication.java`**:

```java
package com.example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventsDemoApplication.class, args);
    }
}
```

`@SpringBootTest(webEnvironment=NONE)` tests do not start an embedded web server. The main class supplies `@SpringBootConfiguration` and component scanning for the service and listener.

### 6.4. Two Event Types as Java Records

File **`src/main/java/com/example/events/OrderPlacedEvent.java`**:

```java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        int quantity,
        String correlationId) {
}
```

File **`src/main/java/com/example/events/OrderCancelledEvent.java`**:

```java
package com.example.events;

public record OrderCancelledEvent(
        String orderId,
        String reason,
        String correlationId) {
}
```

Both events are **payload objects**, not extending `ApplicationEvent`. `ApplicationEventPublisher.publishEvent(Object)` supports this form; Spring listeners can receive the record directly. Records are shallowly immutable (and all field types here are immutable), making them ideal for observing history and checking equality in tests.

### 6.5. `CheckoutService`: Publish After Input Validation

File **`src/main/java/com/example/events/CheckoutService.java`**:

```java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ApplicationEventPublisher publisher;

    public CheckoutService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void placeOrder(
            String orderId, int quantity, String correlationId) {

        requireText(orderId, "orderId");
        requireText(correlationId, "correlationId");

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        publisher.publishEvent(
                new OrderPlacedEvent(
                        orderId, quantity, correlationId));
    }

    public void cancelOrder(
            String orderId, String reason, String correlationId) {

        requireText(orderId, "orderId");
        requireText(reason, "reason");
        requireText(correlationId, "correlationId");

        publisher.publishEvent(
                new OrderCancelledEvent(
                        orderId, reason, correlationId));
    }

    private static void requireText(
            String value, String field) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must be non-blank");
        }
    }
}
```

The service publishes **exactly one event per valid method invocation**. It has no DB persistence, idempotency, or deduplication. Therefore, two calls with the same `orderId` still publish **two events**—that is a **demo characteristic**, not a claim that duplicate events are safe in production. If the domain requires an exactly-once business transition, enforce invariants/idempotency and test persisted/outbox state.

### 6.6. Listener Counting and Storing Handled Payloads

File **`src/main/java/com/example/events/OrderEventObserver.java`**:

```java
package com.example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventObserver {

    private final List<OrderPlacedEvent> placed =
            new CopyOnWriteArrayList<>();
    private final List<OrderCancelledEvent> cancelled =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onPlaced(OrderPlacedEvent event) {
        placed.add(event);
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        cancelled.add(event);
    }

    public List<OrderPlacedEvent> placed() {
        return List.copyOf(placed);
    }

    public List<OrderCancelledEvent> cancelled() {
        return List.copyOf(cancelled);
    }

    public void clear() {
        placed.clear();
        cancelled.clear();
    }
}
```

Listener methods return `void` so they do not accidentally publish a new event from a return value. `CopyOnWriteArrayList` is safe for simple cross-thread reads/writes, but **does not automatically ensure test isolation when multiple tests run in parallel on the same singleton Spring context**. This JUnit example suite assumes default sequential execution. In projects with JUnit parallel execution, use a collector keyed by `correlationId`, per-test scope, or a dedicated fake listener instead of calling `clear()` on a singleton shared by other tests.

**Different pieces of evidence:** `events.stream(OrderPlacedEvent.class).count()` proves how many **publications** Spring TestContext observed; `observer.placed().size()` proves the corresponding listener **processed up to the append point**. These two numbers only match for successful synchronous listeners without filters; do not assume they match in production with async execution, transaction phases, or consumer retries.

### 6.7. Spring Integration Tests: 13 Test Methods

File **`src/test/java/com/example/events/CheckoutEventIntegrationTest.java`**:

```java
package com.example.events;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class CheckoutEventIntegrationTest {

    @Autowired
    private CheckoutService service;

    @Autowired
    private OrderEventObserver observer;

    @BeforeEach
    void reset(ApplicationEvents events) {
        events.clear();
        observer.clear();
    }

    @Test
    void onePlacementHasExactTypeAndPayload(
            ApplicationEvents events) {

        service.placeOrder("ORD-1", 2, "REQ-1");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(new OrderPlacedEvent(
                        "ORD-1", 2, "REQ-1"));
    }

    @Test
    void listenerHandlesExactlyOneMatchingPlacedEvent(
            ApplicationEvents events) {

        service.placeOrder("ORD-2", 5, "REQ-2");

        OrderPlacedEvent expected =
                new OrderPlacedEvent("ORD-2", 5, "REQ-2");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).containsExactly(expected);
    }

    @Test
    void placementDoesNotEmitCancellation(
            ApplicationEvents events) {

        service.placeOrder("ORD-3", 1, "REQ-3");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
        assertThat(observer.cancelled()).isEmpty();
    }

    @Test
    void twoDistinctPlacementsEmitExactlyTwoInOrder(
            ApplicationEvents events) {

        service.placeOrder("ORD-A", 1, "REQ-A");
        service.placeOrder("ORD-B", 3, "REQ-B");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(
                    new OrderPlacedEvent("ORD-A", 1, "REQ-A"),
                    new OrderPlacedEvent("ORD-B", 3, "REQ-B"));

        assertThat(observer.placed()).hasSize(2);
    }

    @Test
    void twoCallsWithSameIdAreVisibleAsTwoPublications(
            ApplicationEvents events) {

        service.placeOrder("ORD-SAME", 1, "REQ-A");
        service.placeOrder("ORD-SAME", 1, "REQ-B");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(2L);
        assertThat(observer.placed()).hasSize(2);
        // Demo does not dedupe; production requires idempotency if needed.
    }

    @Test
    void cancellationEmitsOnlyCancellationTypeWithPayload(
            ApplicationEvents events) {

        service.cancelOrder("ORD-9", "customer-request", "REQ-9");

        assertThat(events.stream(OrderCancelledEvent.class).toList())
                .containsExactly(new OrderCancelledEvent(
                        "ORD-9", "customer-request", "REQ-9"));
        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(observer.cancelled()).hasSize(1);
    }

    @Test
    void mixedBusinessTypesAreCountedSeparately(
            ApplicationEvents events) {

        service.placeOrder("ORD-10", 1, "REQ-10");
        service.cancelOrder("ORD-10", "changed-mind", "REQ-11");
        service.placeOrder("ORD-11", 4, "REQ-12");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(2L);
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).hasSize(2);
        assertThat(observer.cancelled()).hasSize(1);
    }

    @Test
    void blankOrderIdDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder(" ", 1, "REQ-BAD"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(observer.placed()).isEmpty();
    }

    @Test
    void zeroQuantityDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder("ORD-BAD", 0, "REQ-BAD"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
    }

    @Test
    void blankCorrelationIdDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder("ORD-BAD", 1, ""))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
    }

    @Test
    void blankCancellationReasonDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.cancelOrder("ORD-12", "", "REQ-12"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
    }

    @Test
    void clearStartsNewRecordedWindowButNotListenerReset(
            ApplicationEvents events) {

        service.placeOrder("ORD-BEFORE", 1, "REQ-BEFORE");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).hasSize(1);

        events.clear(); // Does not undo listener side effect.

        service.placeOrder("ORD-AFTER", 2, "REQ-AFTER");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(new OrderPlacedEvent(
                        "ORD-AFTER", 2, "REQ-AFTER"));
        assertThat(observer.placed()).hasSize(2);
    }

    @Test
    void typedBusinessStreamStartsEmptyAfterReset(
            ApplicationEvents events) {

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
        assertThat(observer.placed()).isEmpty();
        assertThat(observer.cancelled()).isEmpty();
        // Do not assert events.stream().count() == 0:
        // framework/test lifecycle may publish other events.
    }
}
```

These **13 `@Test` methods** show: each test has its own `ApplicationEvents`, reset via `events.clear()`, the observer is also reset, both positive and negative cases are covered, and publication counts are checked **per event type**. Never assert the total of all Spring framework events. `clearStartsNewRecordedWindowButNotListenerReset` proves that resetting the event log **does not erase what the listener already processed**.

### 6.8. Mockito Unit Tests: Checking Publisher Calls Without Running Spring Context

File **`src/test/java/com/example/events/CheckoutServiceUnitTest.java`**:

```java
package com.example.events;

import org.junit.jupiter.api.Test;

import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class CheckoutServiceUnitTest {

    @Test
    void publishesOneExactOrderPlacedPayload() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.placeOrder("ORD-U1", 7, "REQ-U1");

        ArgumentCaptor<OrderPlacedEvent> captor =
                ArgumentCaptor.forClass(OrderPlacedEvent.class);
        verify(publisher, times(1))
                .publishEvent(captor.capture());

        assertThat(captor.getValue()).isEqualTo(
                new OrderPlacedEvent("ORD-U1", 7, "REQ-U1"));
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidInputNeverCallsPublisher() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        assertThatThrownBy(() ->
                service.placeOrder("", 1, "REQ-U2"))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(publisher);
    }

    @Test
    void cancelUsesCancellationEventNotPlacedType() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.cancelOrder("ORD-U3", "duplicate", "REQ-U3");

        ArgumentCaptor<OrderCancelledEvent> captor =
                ArgumentCaptor.forClass(OrderCancelledEvent.class);
        verify(publisher, times(1))
                .publishEvent(captor.capture());

        assertThat(captor.getValue()).isEqualTo(
                new OrderCancelledEvent(
                        "ORD-U3", "duplicate", "REQ-U3"));
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void twoInvocationsCallPublisherTwice() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.placeOrder("ORD-U4", 1, "REQ-U4");
        service.placeOrder("ORD-U5", 2, "REQ-U5");

        verify(publisher, times(2))
                .publishEvent(any(OrderPlacedEvent.class));
        verifyNoMoreInteractions(publisher);
    }
}
```

These **4 `@Test` methods** serve a different goal than the integration suite: Mockito only observes calls to `ApplicationEventPublisher.publishEvent(...)`, creates no Spring ApplicationContext, and performs no real dispatch to listeners. `ArgumentCaptor` allows asserting type/payload/count right at the publication boundary. Unit tests are usually faster and great for checking that each business branch publishes properly. However, **verifying the publisher does not prove the listener ran**, let alone an external broker or side effects.

In Java, `ApplicationEventPublisher` overloads `publishEvent(ApplicationEvent)` and `publishEvent(Object)`; the event records in the demo **do not extend `ApplicationEvent`**, so `publishEvent(captor.capture())` and `publishEvent(any(OrderPlacedEvent.class))` target the `Object` overload, and Mockito observes them cleanly.

### 6.9. Running, Expectations, and Limitations

Requires JDK 17+, Maven, no Docker:

```bash
mvn test
mvn -Dtest=CheckoutEventIntegrationTest test
mvn -Dtest=CheckoutServiceUnitTest test
```

If the project has a Maven Wrapper: `./mvnw test` (Linux/macOS) or `mvnw.cmd test` (Windows). Based on the sample code, expect **13 integration + 4 unit = 17 JUnit tests**, with no failures/errors. The tests use fixed data and synchronous event dispatch in the default context, so neither `Thread.sleep` nor awaiting eventual state is needed.

**There is no fixed business stdout.** Maven Surefire and Spring context logs vary by version/configuration. The code has been checked against Spring Framework 6.2/Spring Boot 3.5/Java 17 APIs; **this is not a claim that Maven has been executed**. In real usage, run in your project/CI and verify your Spring test listeners and event multicaster configuration.

## 7. Distinguishing Publish Count, Listener Invocation Count, and Side Effects

| Metric | What Does It Mean? | Testing Tool | What It Does Not Prove |
|---|---|---|---|
| Publisher call count | How many times the service called `publishEvent` | Mockito `verify(..., times(n))` | Listener actually ran |
| Recorded application event count | How many payload events of that type Spring TestContext saw | `@RecordApplicationEvents` + `events.stream(Type.class).count()` | Listener/consumer finished |
| Listener handled count | Listener entered code and reached a specific checkpoint | Fake collector/spy, counter/sink | External email/Kafka delivered |
| External command count | How many times an adapter called Kafka/email/HTTP APIs | Fake gateway, broker recorder/test double | Provider processed correctly |
| Persisted outcome count | Number of rows/outbox messages after commit | DB integration test + cleanup | Kafka consumer received exactly once |
| End-user/business outcome | Business action satisfied its invariant | End-to-end/saga/integration tests | Event bus alone provides exactly-once |

For example, with **one event** and **two listeners**: publication count = 1, but total listener invocations may = 2. Or a listener itself emits `AuditEvent`, making total events = 2 even though the command published `OrderPlacedEvent` once. A listener with a `condition` only runs when data matches; recorded count can still be 1 while handled count = 0.

**Do not write `Mockito.verify(listener, times(1))` and call it “the publisher emitted exactly once”.** That only proves the listener method was invoked once on the spy/mock, possibly via another call path, and does not prove what payload type was published. Conversely, `@RecordApplicationEvents` shows publication but does not guarantee listener success if async or transacted.

### `@EventListener` Can Publish a New Event from Its Return Value

An example to avoid unless intentional:

```java
@EventListener
public AuditEvent handle(OrderPlacedEvent placed) {
    return new AuditEvent(placed.orderId(), "PLACED");
}
```

This is a **snippet** requiring an `AuditEvent` class definition and imports; it is not in the runnable demo. Under Spring `@EventListener` semantics, a non-`void` return value can be published as a follow-up event. If a test counts `events.stream().count()`, it will see more events than expected; filter by specific type and verify whether business listeners are supposed to emit follow-up events.

If a listener both writes to the DB and returns `AuditEvent`, tests must distinguish: did the event appear on the bus, did the listener write successfully, or did an outbox commit? Returning an event does not provide transaction atomicity.

## 8. Transaction-Bound Events: Publishing Happens Before Commit

Spring provides `@TransactionalEventListener` with phases:

- `BEFORE_COMMIT`: before commit.
- `AFTER_COMMIT` (**default**): runs after the transaction commits successfully.
- `AFTER_ROLLBACK`: runs after rollback.
- `AFTER_COMPLETION`: after the transaction finishes, whether commit or rollback.

Example:

```java
@Component
class NotificationHandler {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    void notifyAfterCommit(OrderPlacedEvent event) {
        // Runs only when the transaction containing the publication COMMITS.
        // This is a snippet, not a full runnable component.
    }
}
```

If **no transaction is active**, a transactional listener **does not run** by default; you can choose `fallbackExecution=true` if the business contract allows execution outside a transaction. Weigh the requirement carefully; do not add fallback arbitrarily just to make a test green.

### Why Are `@Transactional` Tests Often Misunderstood?

A Spring test annotated with `@Transactional` is typically rolled back by TestContext at the end of the test. If a service publishes an event inside that transaction:

```text
@Transactional test begins
       |
       +-- service publishes OrderPlacedEvent
       |       |
       |       +-- @RecordApplicationEvents sees publish: count=1
       |
       +-- @TransactionalEventListener(AFTER_COMMIT)
       |       |
       |       +-- NOT YET run because not committed
       |
       +-- test ends -> rollback
               |
               +-- AFTER_COMMIT listener DOES NOT run
```

Thus, **recorded publication count=1** and **after-commit listener count=0** can both be true. This is not a Spring event bus bug. If your goal is to test that the listener runs after commit, you must **explicitly commit a test transaction**, such as using Spring's `TestTransaction` in a `@Transactional` test with a real transaction manager, or using `TransactionTemplate` with an appropriate test database/transaction manager. Do not sprinkle `@Commit` carelessly and pollute a shared DB; clean up by test ID.

With `TestTransaction`, conceptual flow (snippet, not standalone runnable):

```java
// Test managed by Spring TestContext, with
// @Transactional and a real PlatformTransactionManager.
service.placeOrder("ORD-1", 1, "REQ-1");

TestTransaction.flagForCommit();
TestTransaction.end();   // commit: AFTER_COMMIT can now execute

// Assert listener side effect / state after commit.
// To open a new transaction if needed: TestTransaction.start().
```

**Important:** `@RecordApplicationEvents` records **publication** and does not verify commit, listener side effects, or DB persistence. If an `AFTER_COMMIT` listener needs to write new data to the DB, transaction resources may still be accessible even though the transaction has ended; per Spring docs, a new transaction (`REQUIRES_NEW`) is typically needed for writes. Do not assume every write inside AFTER_COMMIT commits by default.

With reactive transactions, the transaction context lives in the Reactor Context rather than being thread-bound like an imperative transaction manager; follow `TransactionalEventPublisher` and reactive testing guidance if using WebFlux/R2DBC.

## 9. Async Listeners and Timing Conditions in Tests

A listener can be configured with `@Async @EventListener`, or the event multicaster may have a task executor. In that case:

1. Calling `publishEvent` can return **before the listener finishes executing**.
2. `@RecordApplicationEvents` may have recorded the publication in the test while the listener side effect is not yet done.
3. Immediately asserting listener count right after publication can be flaky.
4. An exception thrown in an async listener may be handled by the executor/error handler and **not propagate back to the JUnit test thread**.
5. `ApplicationEvents` recording scope is tied to the test method lifecycle and the test thread/descendant threads per Spring TestContext. Do not rely on recording events emitted from an arbitrary worker after the test completes.
6. When tests involve multiple event types in parallel pipelines, global publish/consume order is not always deterministic.

### How to Test Async Listeners Properly

Use **bounded acknowledgement** instead of `Thread.sleep(1000)`:

```text
Test thread                       Async listener
     |                                   |
     +-- publish(event) ---------------->|
     |                                   +-- process event
     |                                   +-- completion.complete(result)
     |
     +-- completion.get(5, SECONDS) <----+
     +-- assert processed type/payload/count
```

When a test uses a fake listener, it can expose a `CompletableFuture<Void>` or `CountDownLatch` signaled after real processing completes. The test waits with `get(timeout)`/`await(timeout)`, checks worker failures via `completeExceptionally`, and cleans up thread state. Avoid sleep, avoid infinite polling loops, and avoid asserting “listener count=1” before the worker has had a chance to run.

**Caution with `@RecordApplicationEvents` and async:** events emitted from threads outside the test lifecycle or arriving after the test finishes may not be recorded as expected. When what needs to be proven is that the **consumer processed the event**, inspect the consumer's output/acknowledgement rather than only reading recorded events. For event brokers like Kafka/RabbitMQ, use consumer tests, embedded brokers, or Testcontainers as appropriate; do not treat Spring's in-process bus as a stand-in for network delivery.

## 10. Observability: Event Emission Differs from Metrics, Logs, and Traces

An application may have all of these:

- **Domain event**: `OrderPlacedEvent` — business data about a transition.
- **Micrometer counter**: `order.events.published` incremented on publish, potentially tagged with event type/outcome.
- **Observation/span**: trace correlation, latency, status, and errors when instrumented.
- **Audit log**: messages for operators; logs are not an event store.
- **Outbox record**: a reliable record used to publish to a broker after commit.
- **Broker message**: event/message sent through Kafka/RabbitMQ.
- **Consumer acknowledgement**: consumer processed or acked according to broker semantics.

Do not use **log line count** to claim the application published an event once: logging has filters, retries, batching, duplication, async appenders, and level configs. When it matters, test the **publisher boundary directly** with Mockito or `@RecordApplicationEvents`. For metrics, use a test `MeterRegistry` and assert counter deltas before/after the operation (avoiding cross-test leaks), keeping in mind that is **counting metrics**, not a substitute for event payload tests.

### CorrelationId and High Cardinality

`correlationId` in payloads is useful for tracing and reconciling individual operations. When attaching metric tags, **do not** use every `orderId`/`correlationId` as a tag if it generates unbounded values: high cardinality drives up metric costs and creates operational risks. Use finite sets like event type/outcome for tags, and put correlationId in controlled traces/logs while avoiding PII/secrets.

If an event carries sensitive data, do not use the record's `toString()` to log the entire payload. Content tests should also use synthetic values, never hardcoding real tokens, customer names, or payment details.

## 11. QA Scenarios and Common Mistakes

| Mistake in Code/Tests | Why Is It Dangerous? | Evidence or Fix |
|---|---|---|
| Asserting only that service doesn't throw | It might publish nothing | Assert `events.stream(Type.class).count()` |
| Asserting only event count > 0 | Could publish duplicates | Assert count **equals 1** and payload |
| Using only `findFirst()` | Extra events could trail behind | Assert `containsExactly(...)` or count |
| Counting `events.stream().count()` | Mixes in framework/test/lifecycle events | Filter `events.stream(DomainType.class)` |
| Asserting `toString()` text | Not type-safe, brittle to formatting changes | Assert record equality/fields |
| Not checking opposing event types | Logic might wrongly emit cancellation | Assert target type present, wrong type absent |
| Treating listener count = 1 as publish count | Multiple listeners or conditions change the count | Test publisher and listener at their own boundaries |
| Using Mockito publisher mock to claim real listener runs | Mock never dispatches | Add `@SpringBootTest` + `@RecordApplicationEvents` |
| Using `@RecordApplicationEvents` alone to claim Kafka sent | In-process events don't imply broker delivery | Broker/adapter integration test |
| Missing `@RecordApplicationEvents` | `ApplicationEvents` not wired for the test | Add annotation and keep default TestExecutionListener |
| Replacing `@TestExecutionListeners` and dropping defaults | Loses ApplicationEventsTestExecutionListener | Merge defaults or register listener explicitly |
| Using `clear()` expecting to undo listener | clear only resets recorded history | Reset fake observer/DB state separately |
| Context cache + singleton observer, parallel tests | State leaks across tests | Per-test correlation/isolation or disable parallel |
| Relying on order across async publishers | Race across threads | `containsExactlyInAnyOrder` if order isn't a contract |
| Asserting listener ran right after async publish | Handler hasn't finished yet | Bounded latch/future, no sleep |
| `@Transactional` rollback test expecting AFTER_COMMIT listener | No commit occurs | TestTransaction/TransactionTemplate with real commit |
| Emitting event before tx commit and expecting exactly-once DB outcome | Rollback after publish leaves event emitted | Transaction-bound event/outbox/compensation |
| Non-void listener accidentally republishes event | Spring publishes return value | Use void or test follow-up event explicitly |
| Event processed multiple times due to caller retry | No idempotency/dedup | Stable operation ID, stateful integration tests |
| Asserting exact `Instant.now()` timestamps | Flaky due to scheduling | Inject Clock or reasonable tolerance |
| Counting Spring context events as domain events | Startup creates non-business events | Use event type and correlation ID |
| Logging raw event payloads | Can leak PII/secrets | Redact and enforce log-level policy |
| Tests don't cover invalid commands | May publish after failed validation | Negative tests: invalid input -> 0 events |
| Service publishes 2 events but test asserts 1 match | Extra emissions ignored | Assert exact count + wrong types + listener checkpoint |

### Troubleshooting Process When Event Count Is Wrong

1. **Identify the boundary**: are you verifying publishing at the service, dispatch to a Spring listener, or message delivery to a broker?
2. **Count by concrete type** using `ApplicationEvents.stream(EventType.class)` or publisher call verification, not total framework events.
3. **Attach correlation/aggregate IDs** per operation; is emitting multiple events of the same type the business contract or a retry?
4. **Inspect the full payload**: which method builds the values, and could it return default fields or the wrong ID?
5. **Check listener side effects separately**: are there `@EventListener(condition=...)`, multiple listeners, async, or transactional phases?
6. **Verify transaction boundaries**: is the event published before or after commit? Does a `@Transactional` test roll back?
7. **Check duplicate emission sources**: service publishing in two places, listener return values, controller/service retries, duplicate requests, broker redelivery.
8. **Isolate test state**: `@BeforeEach` resets recorder/observer; if parallel, use per-test IDs and synchronized collectors instead of singleton clear.
9. **Keep assertions strict**: exact count, exact payload, and expected absent types; do not loosen to `isNotEmpty()` just to make a test pass.
10. **Separate observability from delivery guarantees**: an accurate event counter does not mean email/DB/outbox/Kafka succeeded.

## 12. Extension: Testing Events Using an ApplicationEvent Subclass

Not every event is a record payload. You can also define a class extending `ApplicationEvent`:

```java
public class InventoryChangedEvent extends ApplicationEvent {

    private final String sku;

    public InventoryChangedEvent(Object source, String sku) {
        super(source);
        this.sku = sku;
    }

    public String getSku() {
        return sku;
    }
}
```

This is a **snippet** requiring `import org.springframework.context.ApplicationEvent` and an enclosing package; it is not in the runnable demo. With such a subclass, the Spring publisher uses `publishEvent(ApplicationEvent)`, and `ApplicationEvents.stream(InventoryChangedEvent.class)` filters by the event class directly without unwrapping a payload object.

**Which should you choose?** With Java 17 and simple domain events, record payloads are convenient because they are immutable and easy to compare in tests. Extending `ApplicationEvent` is useful if you genuinely need event metadata/source in the traditional class style. Avoid using `ApplicationEvent.getSource()` to hold sensitive data or grant authority; it does not provide durable event schema guarantees.

## 13. Checklist for Event and Observability Tests

- [ ] The specification clearly defines the **event boundary**: publisher, Spring listener, broker, outbox, or external side effect.
- [ ] Tests have `@RecordApplicationEvents` and the default `ApplicationEventsTestExecutionListener`.
- [ ] Tests use `events.stream(ExactEventType.class)`, rather than counting all Spring events.
- [ ] Event type is exact and not confused with another event type.
- [ ] Payloads are asserted across **all meaningful fields**, not just `notNull` or `toString()`.
- [ ] Event counts are exact: 0, 1, 2... per business operation.
- [ ] Includes positive cases for one event and negative cases where invalid input produces 0 events.
- [ ] Includes multi-operation cases to catch missing or duplicate events.
- [ ] Includes tests verifying the payload preserves `correlationId`/aggregate ID.
- [ ] Does not use `findFirst` as a substitute for uniqueness assertions.
- [ ] When verifying publisher unit behavior, uses Mockito `ArgumentCaptor`/`verify(times(n))`.
- [ ] When verifying event dispatch, runs through a real Spring context/`@EventListener`.
- [ ] Listener count is asserted separately, not equated with publication count.
- [ ] Test state is properly reset: `events.clear()` and separate fake listener collector.
- [ ] If contexts are cached / JUnit runs in parallel, uses proper ID-based isolation and thread safety.
- [ ] Tests account for non-void `@EventListener` methods potentially republishing events.
- [ ] If using `@TransactionalEventListener`, AFTER_COMMIT/ROLLBACK are tested against a real transaction.
- [ ] Does not expect AFTER_COMMIT to run when a Spring test transaction rolls back.
- [ ] For async listeners, waits via bounded future/latch rather than Thread.sleep.
- [ ] If events go to Kafka/RabbitMQ, separate integration tests cover broker delivery/retry/dedup.
- [ ] Does not infer DB commit, listener success, or external delivery solely from a recorded event.
- [ ] Metrics/logs/traces are separate observability signals; do not replace event payload tests with log counts.
- [ ] Does not create high-cardinality metric tags with orderId/correlationId.
- [ ] Does not log payloads with secrets/PII; test data uses synthetic values.
- [ ] Ran `mvn test` on JDK 17+ / Boot 3.5 and reviewed the production event multicaster config.

**Conclusion:** To prove Spring Boot publishes events properly, verify the **exact type, exact content, and exact count** inside an isolated test window. `@RecordApplicationEvents` + `ApplicationEvents.stream(EventType.class)` is a strong tool for integration tests, while Mockito `ArgumentCaptor` fits publisher unit tests. **Never equate a published event with a completed listener, a committed transaction, or a message delivered to an external system.** Those require additional evidence and tests at their respective boundaries.

### Official Documentation

- [Spring Framework 6.2 — Application Events in TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — ApplicationEvents Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — Standard and Custom Events / @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Mockito — ArgumentCaptor API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ArgumentCaptor.html)
