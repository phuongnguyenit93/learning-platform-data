# Testing Payloads and Properties in Spring Framework Application Events

## 1. Learning Objectives

In a Spring application, verifying that a listener was called is **not enough** to conclude an event is correct. For instance, `OrderPlaced` may have been published once yet carry the wrong `orderId`, wrong `correlationId`, inaccurate timestamp, or a product list mutated after publication. A solid test must inspect the **payload contents, properties/metadata, and delivery contract** of the event.

After this lesson, you will be able to:

1. Distinguish testing **emitted events** from testing **listener handling**.
2. Accurately verify **event type, emission count, component values, metadata, timestamps, and identifier relationships**.
3. Use `@RecordApplicationEvents` and `ApplicationEvents.stream(Class<T>)` in Spring TestContext with JUnit 5.
4. Test POJO/record payloads published via `publishEvent(Object)` as well as traditional events extending `ApplicationEvent`.
5. Test **immutable snapshots**, validation, nulls, enums, collections, and scenarios where the same `eventId` is emitted repeatedly.
6. Avoid flaky tests when listeners are asynchronous or when events are bound to transactions.
7. Know when to test at the domain layer, the Spring infrastructure layer, or the consumer performing side effects.

This topic belongs to the **Event Testing** group in Spring Framework Application Events. It focuses on **payloads and properties** rather than merely checking whether a callback executed.

## 2. What Payloads and Properties Should Be Tested?

The **payload** is the data an event delivers to consumers, such as the record:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId,
        String causationId,
        Instant occurredAt,
        int schemaVersion,
        List<OrderLine> lines
) {}
```

This is a data-type sketch; constructor validation and defensive copying appear in the full example in section 6.

**Properties** can span three layers:

| Layer | Examples | Appropriate Check |
| --- | --- | --- |
| Business data | `orderId`, `sku`, `quantity`, `unitPrice` | Values match inputs and business rules |
| Metadata inside payload | `eventId`, `correlationId`, `causationId`, `occurredAt`, `schemaVersion` | Accurate IDs, preserved correlation, fixed fixture time, valid version |
| Framework properties | Event type, `ApplicationEvent.getSource()`, `getTimestamp()`, `PayloadApplicationEvent.getPayload()` | Spring dispatches the right type and the wrapper matches its contract |

**Do not confuse** the domain event's `occurredAt` with `ApplicationEvent.getTimestamp()`. `occurredAt` is created by the application to represent **business time**, whereas `ApplicationEvent`'s timestamp is assigned by the framework when the event instance is constructed. They may differ and should not be asserted against a hardcoded number.

### Which Questions Must Be Verified?

- **Type:** was `OrderPlaced` emitted rather than `OrderCancelled`?
- **Count:** exactly one event or multiple events? Was there unintended duplicate publishing?
- **Identity:** right `eventId` for the occurrence, right `orderId` for the aggregate?
- **Causality:** does `correlationId` preserve the workflow, and does `causationId` point to the parent event when present?
- **Timestamp:** did `occurredAt` come from business logic or get regenerated in a listener?
- **Contents:** are quantities, prices, status enums, and element sets accurate?
- **Immutability:** if the caller mutates a list after publishing, does the emitted payload remain unchanged?
- **Validation:** is invalid data rejected before the event is published?
- **Framework contract:** does the listener receive the exact POJO record? For an `ApplicationEvent` subclass, is `source` the expected object?

## 3. Distinguishing Three Testing Levels

| Level | Test Target | Evidence Gained | Does Not Automatically Prove |
| --- | --- | --- | --- |
| Record/constructor unit test | Immutability, validation, defensive copying | The payload is valid on its own | Spring actually published the event |
| TestContext integration test | Service calls `ApplicationEventPublisher`; `ApplicationEvents` records | Spring emitted the right type and right data | External APIs, database, or async jobs definitely succeeded |
| Consumer/flow integration test | Real listeners, transactions, queues, side effects | Handlers perform side effects per contract | End-to-end exactly-once or durable delivery without dedicated design |

An overly weak counterexample test:

```java
@Test
void weakTest() {
    OrderPlaced event = buildFixture();
    listener.onOrderPlaced(event);
    // This test only proves the Java method was called directly,
    // not that the service published the right event via Spring.
}
```

The snippet above is **illustrative code**, requiring concrete fixtures/listeners to run. To test event publication, invoke **the service behavior that emits the event** and observe events from the application context instead of constructing an event and calling the callback directly.

## 4. Spring TestContext Tool: @RecordApplicationEvents

Since version 5.3.3, Spring Framework provides built-in recording of application events during tests:

- `@SpringJUnitConfig`: annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`, enabling JUnit Jupiter to run with Spring TestContext.
- `@RecordApplicationEvents`: enables event recording for each test method.
- `ApplicationEvents`: API to read recorded events, offering `stream()`, `stream(Class<T>)`, and `clear()`.
- `ApplicationEventsTestExecutionListener`: TestContext component supporting recording; registered by default in standard listener configurations.

Sample usage:

```java
@SpringJUnitConfig(TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    OrderService service;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        events.clear(); // Inspect only events from this point onward.
        service.placeOrder();

        assertEquals(1,
                events.stream(OrderPlaced.class).count());
    }
}
```

This is an **illustrative excerpt** requiring corresponding `TestConfig`, `OrderService`, and `OrderPlaced`. The runnable example in section 6 provides complete configuration and classes.

### Why Is ApplicationEvents.stream(Class<T>) Needed?

`events.stream()` returns a stream of framework `ApplicationEvent`s, which can include startup/context events or other test events. In contrast, `events.stream(OrderPlaced.class)` filters **events or payloads matching the type of interest**, letting you inspect records/POJOs published via `publishEvent(Object)`.

Example:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("ORD-42", placed.get(0).orderId());
```

A payload test must **extract the actually recorded event** to assert its values rather than calling only `count()`. Counting one event that carries the wrong `orderId` or amount is still a bug.

### Do Not Misuse Lifecycle Scope

According to Spring TestContext, `ApplicationEvents` is bound to **the current test method's lifecycle**. With JUnit Jupiter, the simplest way is accepting `ApplicationEvents` via a `@Test` or `@BeforeEach`/`@AfterEach` parameter. Field injection in tests is also supported; **do not inject ApplicationEvents into the test class constructor or into a singleton service inside the application context to hold permanently**.

`events.clear()` is useful before the behavior under test when a test has setup events; it clears recorded events **in the current test instance**, without deleting messages on a broker or altering business data.

## 5. Build a Test Matrix Before Writing Code

For `OrderPlaced`, a minimal matrix:

| Case | Action | Expectation |
| --- | --- | --- |
| Valid publish | Call `OrderService.place(...)` | Exactly one `OrderPlaced` |
| Metadata | Publish with deterministic IDs and timestamp | Fields match exactly |
| Nested values | One line `SKU-7`, quantity 2, price 75.00 | List contains exact line; computed total is 150.00 |
| Snapshot | Mutate source list after publish | Recorded payload does not change |
| Mutation resistance | Call `event.lines().clear()` | Rejected with `UnsupportedOperationException` |
| Event type | Publish `OrderCancelled` | `stream(OrderPlaced.class)` is empty |
| Validation | Pass blank `orderId` | Constructor throws; no `OrderPlaced` published |
| Duplicate occurrence | Publish twice with same `eventId` | Two emissions occur; Spring does not auto-deduplicate |
| Framework source | Publish `OrderFlaggedEvent extends ApplicationEvent` | `getSource()` is the object chosen when creating the event |
| Framework timestamp | Inspect `getTimestamp()` | Valid value at creation time; do not hardcode epoch millis |

For other event families, the matrix can add status enums, aggregate versions, multi-tenant IDs, currencies, schema versions, empty/null collections, causation of derived events, and domain-specific invariants.

## 6. Complete Example: Java 17, Spring Framework 6.2, and JUnit 5

This project uses **plain Spring Framework**, without requiring Spring Boot, a web server, or a database.

The sample application contains:

1. Records `OrderLine` and `OrderPlaced` with validation and `List.copyOf`.
2. Record `OrderCancelled` to test event-type separation.
3. Class `OrderFlaggedEvent` extending `ApplicationEvent` to test `getSource()` and `getTimestamp()`.
4. `OrderService` emitting events via `ApplicationEventPublisher`.
5. `RecordingListener` receiving `OrderPlaced` via `@EventListener` to confirm Spring delivers the record payload to listeners.
6. A JUnit 5 suite using `@SpringJUnitConfig` + `@RecordApplicationEvents`, testing **five scenarios**.

The example chooses a fixed `occurredAt`, uses a single context configured via `@Bean`, and relies on the **default synchronous multicaster**. This keeps results deterministic without `sleep`.

### 6.1. Directory Structure

```text
spring-event-payload-test/
├── pom.xml
└── src/
    ├── main/java/example/OrderEventModule.java
    └── test/java/example/OrderPayloadEventsTest.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-event-payload-test</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.3</version>
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

### 6.3. File src/main/java/example/OrderEventModule.java

```java
package example;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class OrderEventModule {

    private OrderEventModule() {}

    public record OrderLine(
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be negative");
            }
        }
    }

    // POJO/record payload, does not extend ApplicationEvent.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String correlationId,
            String causationId,
            Instant occurredAt,
            int schemaVersion,
            List<OrderLine> lines) {

        public OrderPlaced {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(correlationId, "correlationId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank()
                    || orderId.isBlank()
                    || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "required ID is blank");
            }
            if (schemaVersion < 1) {
                throw new IllegalArgumentException(
                        "schemaVersion must be positive");
            }

            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "order must have at least one line");
            }
        }
    }

    public record OrderCancelled(
            String eventId,
            String orderId,
            String reason) {}

    // Legacy Spring event type to test getSource/timestamp.
    public static final class OrderFlaggedEvent
            extends ApplicationEvent {
        private final String orderId;

        public OrderFlaggedEvent(Object source, String orderId) {
            super(source);
            this.orderId =
                    Objects.requireNonNull(orderId, "orderId");
        }

        public String orderId() {
            return orderId;
        }
    }

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(
                String eventId,
                String orderId,
                String correlationId,
                String causationId,
                Instant occurredAt,
                int schemaVersion,
                List<OrderLine> lines) {

            // Validate and create snapshot before publishing.
            OrderPlaced event = new OrderPlaced(
                    eventId, orderId, correlationId,
                    causationId, occurredAt, schemaVersion, lines);
            publisher.publishEvent(event);
        }

        public void cancel(String eventId,
                           String orderId,
                           String reason) {
            publisher.publishEvent(
                    new OrderCancelled(eventId, orderId, reason));
        }

        public void flag(String orderId) {
            // Deliberately choose the service as the source object.
            publisher.publishEvent(
                    new OrderFlaggedEvent(this, orderId));
        }
    }

    public static class RecordingListener {
        private final CopyOnWriteArrayList<OrderPlaced> received =
                new CopyOnWriteArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
        }

        public List<OrderPlaced> received() {
            return List.copyOf(received);
        }

        public void clear() {
            received.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public RecordingListener recordingListener() {
            return new RecordingListener();
        }
    }
}
```

**Explanation of key parts:**

- `OrderPlaced` and `OrderLine` are Java 17 records. Compact constructors validate IDs, quantity, price, and take a `List.copyOf(lines)` snapshot.
- `OrderService.place(...)` constructs the event **first** and then publishes. If the constructor throws, publishing never happens.
- Spring supports `publishEvent(Object)`. When receiving a record that does not extend `ApplicationEvent`, the infrastructure can wrap it in `PayloadApplicationEvent<OrderPlaced>`; `@EventListener` listeners still receive **`OrderPlaced` directly**.
- `OrderFlaggedEvent` uses `super(source)` to test the API of a traditional `ApplicationEvent`. This is a different mechanism from `correlationId` metadata inside the record.
- `RecordingListener` is a real bean verifying the delivery path to listeners. Because tests run synchronously by default, it captures the event before `place(...)` returns. `CopyOnWriteArrayList` only makes the recorder safe if read from another thread later; there is no waiting mechanism for async here.
- All beans are declared via `@Bean` in `Config`, independent of component scanning or an external Spring Boot application.

### 6.4. File src/test/java/example/OrderPayloadEventsTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.OrderEventModule.OrderCancelled;
import example.OrderEventModule.OrderFlaggedEvent;
import example.OrderEventModule.OrderLine;
import example.OrderEventModule.OrderPlaced;

@SpringJUnitConfig(OrderEventModule.Config.class)
@RecordApplicationEvents
class OrderPayloadEventsTest {

    private static final Instant OCCURRED_AT =
            Instant.parse("2026-11-01T08:00:00Z");

    @Autowired
    OrderEventModule.OrderService service;

    @Autowired
    OrderEventModule.RecordingListener recorder;

    @BeforeEach
    void resetRecorder() {
        // Bean is a singleton and TestContext can cache contexts.
        recorder.clear();
    }

    private static OrderLine sampleLine() {
        return new OrderLine(
                "SKU-7", 2, new BigDecimal("75.00"));
    }

    // Test 1: type, payload, properties, and snapshot.
    @Test
    void recordsExactPayloadAndProperties(ApplicationEvents events) {
        events.clear();

        List<OrderLine> draft =
                new ArrayList<>(List.of(sampleLine()));

        service.place(
                "evt-100", "ORD-42", "flow-7", null,
                OCCURRED_AT, 1, draft);

        List<OrderPlaced> published =
                events.stream(OrderPlaced.class).toList();
        assertEquals(1, published.size());

        OrderPlaced actual = published.get(0);
        assertAll(
                () -> assertEquals("evt-100", actual.eventId()),
                () -> assertEquals("ORD-42", actual.orderId()),
                () -> assertEquals("flow-7", actual.correlationId()),
                () -> assertNull(actual.causationId()),
                () -> assertEquals(OCCURRED_AT, actual.occurredAt()),
                () -> assertEquals(1, actual.schemaVersion()),
                () -> assertEquals(
                        List.of(sampleLine()), actual.lines())
        );

        // Mutating input after publish does not mutate the emitted snapshot.
        draft.clear();
        assertEquals(1, actual.lines().size());

        // Consumers cannot mutate the list structure inside the record.
        assertThrows(UnsupportedOperationException.class,
                () -> actual.lines().clear());

        // Prove Spring delivers the exact payload to the listener.
        assertEquals(1, recorder.received().size());
        assertSame(actual, recorder.received().get(0));
    }

    // Test 2: another type is not mistaken for OrderPlaced.
    @Test
    void filtersByEventType(ApplicationEvents events) {
        events.clear();

        service.cancel("evt-cancel", "ORD-42", "requested");

        assertEquals(0,
                events.stream(OrderPlaced.class).count());

        List<OrderCancelled> cancelled =
                events.stream(OrderCancelled.class).toList();
        assertEquals(1, cancelled.size());
        assertEquals("ORD-42", cancelled.get(0).orderId());
        assertEquals("requested", cancelled.get(0).reason());
        assertTrue(recorder.received().isEmpty());
    }

    // Test 3: validation failure must prevent publishing.
    @Test
    void rejectsInvalidPayloadBeforePublishing(
            ApplicationEvents events) {
        events.clear();

        assertThrows(IllegalArgumentException.class, () ->
                service.place(
                        "evt-bad", "  ", "flow-7", null,
                        OCCURRED_AT, 1, List.of(sampleLine())));

        assertEquals(0,
                events.stream(OrderPlaced.class).count());
        assertTrue(recorder.received().isEmpty());
    }

    // Test 4: Spring event bus does not auto-deduplicate eventId.
    @Test
    void duplicateEventIdsAreNotAutomaticallyDeduplicated(
            ApplicationEvents events) {
        events.clear();

        for (int i = 0; i < 2; i++) {
            service.place(
                    "evt-same", "ORD-42", "flow-7", null,
                    OCCURRED_AT, 1, List.of(sampleLine()));
        }

        List<OrderPlaced> published =
                events.stream(OrderPlaced.class).toList();

        assertEquals(2, published.size());
        assertEquals(
                List.of("evt-same", "evt-same"),
                published.stream().map(OrderPlaced::eventId).toList());
        assertEquals(2, recorder.received().size());
    }

    // Test 5: legacy ApplicationEvent class properties.
    @Test
    void legacyEventContainsExpectedSourceAndTimestamp(
            ApplicationEvents events) {
        events.clear();

        service.flag("ORD-42");

        List<OrderFlaggedEvent> flags =
                events.stream(OrderFlaggedEvent.class).toList();
        assertEquals(1, flags.size());

        OrderFlaggedEvent event = flags.get(0);
        assertSame(service, event.getSource());
        assertEquals("ORD-42", event.orderId());
        assertTrue(event.getTimestamp() > 0L);
    }
}
```

### 6.5. Running the Tests

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn test
```

The test suite has **5 `@Test` methods**. Provided dependencies download cleanly and tests succeed, Maven Surefire reports an equivalent outcome:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

These are **the outcome fields to check**, not a verbatim guarantee of full stdout: log formatting, line order, dependency/plugin notices, and execution time may vary. With `mvn -q test`, output can be suppressed; check the exit code or report file `target/surefire-reports/example.OrderPayloadEventsTest.txt`.

**Important:** the code is a real test suite, not a demo with `main()`. The right command is `mvn test`, not `mvn exec:java`. Reliable verification is **all assertions PASSING**, not a console message printed by the example.

### 6.6. Analysis of Each Test

**Test 1 — recordsExactPayloadAndProperties**

- Calls the real service, not the listener directly.
- Extracts `OrderPlaced` from `events.stream(OrderPlaced.class)` to confirm this is the exact event Spring recorded.
- Verifies all of `eventId`, `orderId`, `correlationId`, `causationId`, `occurredAt`, `schemaVersion`, and `lines`.
- Verifies `List.copyOf` produces a snapshot independent of mutable `draft`.
- Verifies the payload's `List` cannot be structurally modified by consumers.
- Verifies `RecordingListener` received the exact same payload instance in the demo's synchronous dispatch path.

**Test 2 — filtersByEventType**

- An emitted `OrderCancelled` must not count as `OrderPlaced`.
- The test also verifies `reason`, because an event of the right type with the wrong reason still fails the contract.
- Does not compare arbitrary total event counts with `events.stream().count()` because the test context can emit other events.

**Test 3 — rejectsInvalidPayloadBeforePublishing**

- An `orderId` consisting solely of spaces is invalid.
- `OrderPlaced`'s constructor throws `IllegalArgumentException` before `publisher.publishEvent`.
- Thus no `OrderPlaced` is recorded; both recorders are checked.

**Test 4 — duplicateEventIdsAreNotAutomaticallyDeduplicated**

- Publishing the same `eventId` twice creates two recorded events.
- This is **framework behavior**, not a test bug.
- If the business must never apply the same side effect twice, the consumer must enforce an idempotency key and dedicated deduplication handling.

**Test 5 — legacyEventContainsExpectedSourceAndTimestamp**

- Class `OrderFlaggedEvent` extends `ApplicationEvent`; the constructor sets source to `OrderService`'s `this`.
- Asserts `getSource()` by **identity** (`assertSame`), without guessing source from class names or event payload.
- `getTimestamp()` is generated by the event instance, so do not hardcode a specific epoch; the test only confirms a timestamp was initialized. When business logic needs deterministic timestamps, store `occurredAt` inside the payload and pass a controlled `Clock`/`Instant` in tests.

## 7. Why Distinguish POJO Events from ApplicationEvent?

Spring supports both common styles.

### 7.1. Record or POJO as Payload

```java
public record OrderPlaced(String orderId) {}

publisher.publishEvent(new OrderPlaced("ORD-42"));
```

This is an integration snippet. Spring wraps an object not extending `ApplicationEvent` in `PayloadApplicationEvent<T>` during dispatch. `@EventListener` can receive `OrderPlaced` directly. In Spring TestContext, `ApplicationEvents.stream(OrderPlaced.class)` returns the **payloads** emitted.

Do not assert that the record has `getSource()` or `getTimestamp()` — record `OrderPlaced` simply does not extend `ApplicationEvent`. If you want those two pieces of information as part of the business contract, declare explicit components such as `sourceSystem`/`occurredAt` inside the record.

### 7.2. Subclassing ApplicationEvent

```java
public final class PaymentCapturedEvent extends ApplicationEvent {
    private final String paymentId;

    public PaymentCapturedEvent(Object source, String paymentId) {
        super(source);
        this.paymentId = paymentId;
    }

    public String paymentId() {
        return paymentId;
    }
}
```

This is an illustrative class requiring `import org.springframework.context.ApplicationEvent`; the full program uses `OrderFlaggedEvent` similarly. In this approach, `getSource()` and `getTimestamp()` are `ApplicationEvent` APIs.

**Warning:** `getSource()` holds only the object passed to the constructor; it does not automatically mean `causationId`, the active caller service, current user, or business storage location. Do not misinterpret framework properties.

## 8. Testing Time Properties Properly

Timestamps are a frequent source of flaky tests.

### Counterexample

```java
assertEquals(
        Instant.now(),
        event.occurredAt());
```

Two clock reads cannot reliably return the same nanosecond. This is even **wrong** if `occurredAt` was created before a callback ran or taken from another transaction.

### Approach 1 — Fixture with a Fixed Instant

In the complete example:

```java
private static final Instant OCCURRED_AT =
        Instant.parse("2026-11-01T08:00:00Z");
```

The service receives this value and places it in the event. The test calls `assertEquals(OCCURRED_AT, actual.occurredAt())`, making the result deterministic.

### Approach 2 — Inject Clock When the Service Generates Timestamps

If a domain service must read the time itself, inject `java.time.Clock`:

```java
public class EventFactory {
    private final Clock clock;

    public EventFactory(Clock clock) {
        this.clock = clock;
    }

    public Instant timestamp() {
        return Instant.now(clock);
    }
}
```

This is an illustrative snippet. In tests you can supply `Clock.fixed(Instant.parse("2026-11-01T08:00:00Z"), ZoneOffset.UTC)` to verify values 100% deterministically rather than comparing two `Instant.now()` calls.

### Approach 3 — ApplicationEvent Timestamp

For `ApplicationEvent.getTimestamp()`, tests can confirm it is positive or within a reasonable window if the environment has clear bounds. However, avoid matching an auto-generated timestamp exactly against another clock read afterward. Section 6's example uses the simple check `getTimestamp() > 0L`.

If you need to record **durable, replayable** business time, place `occurredAt` in the payload; framework timestamps do not replace business schema design.

## 9. Testing Collections and Nested Data

A record has `final` fields yet can hold a `List` or mutable object. Testing payload immutability requires checking both directions:

1. **Caller mutates input:** the event retains the earlier snapshot.
2. **Consumer tries to mutate accessor:** the event forbids direct mutation.

`List.copyOf(...)` protects the list structure, yet **does not deep-copy mutable elements**. If an `OrderLine` component holds an entity with setters or an array, the immutable list still holds a mutable object.

For nested data, add tests like:

```java
assertEquals("SKU-7", actual.lines().get(0).sku());
assertEquals(2, actual.lines().get(0).quantity());
assertEquals(
        new BigDecimal("75.00"),
        actual.lines().get(0).unitPrice());
```

This snippet runs inside section 6's test once `actual` exists. `BigDecimal.equals()` compares **scale** as well; `75.0` and `75.00` are mathematically equal yet not `equals`. If business logic compares only monetary values, consider normalizing scale or using `compareTo(...) == 0`; never silently alter equality rules in tests.

With `Map.copyOf`/`Set.copyOf`, watch out for nulls and non-guaranteed iteration order; with arrays, defensively copy in both constructor and accessor if immutability is desired. Tests should adhere to the **public data contract**, avoiding asserting iteration order of a `HashMap`/`Set` when unspecified.

## 10. When Events Have Complex Metadata

In an event chain:

```text
OrderPlaced
  eventId       = evt-100
  correlationId = flow-7
  causationId   = null
          |
          v
InventoryReservationRequested
  eventId       = evt-101
  correlationId = flow-7
  causationId   = evt-100
```

Derived-event tests should assert:

```java
assertNotEquals(root.eventId(), derived.eventId());
assertEquals(root.correlationId(), derived.correlationId());
assertEquals(root.eventId(), derived.causationId());
```

This is a snippet for a case with matching `root` and `derived` records, not part of section 6's runnable program.

Meaning:

- `eventId` identifies a single occurrence and is not shared across distinct new events.
- `correlationId` groups events within the same workflow and is not necessarily an idempotency key.
- `causationId` identifies the direct parent event and is not taken from `ApplicationEvent.getSource()`.
- `aggregateVersion` or `schemaVersion` must be checked according to the actual versioning policy.
- `tenantId`/`sourceSystem` may matter for routing/auditing; test them when part of the contract.

Do not merely assert `eventId != null`; a non-null wrong ID can still prevent the system from linking events.

## 11. Testing Event Type and Count Without Miscounting

Many events can appear in the same test context: `ContextRefreshedEvent`, `PayloadApplicationEvent`, listener-derived events, custom observer events, and more. Therefore:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

is usually the right assertion for "Was there exactly one `OrderPlaced`?". Avoid:

```java
assertEquals(1, events.stream().count());
```

unless you genuinely have a contract that the entire Spring context emits only one event. The second test can fail due to legitimate system events or another event type rather than a bug in the feature under test.

Also avoid asserting based on `events.stream().findFirst()` across **all** events. Filter by type before selecting the event of interest.

### Testing That Validation Failure Emits No Event

A solid test follows this structure:

```text
Arrange: build invalid input
Act: invoke the service behavior
Assert: receive the expected exception
Assert: stream(OrderPlaced.class) is empty
Assert: listener records no side effects
```

If you test only that the constructor throws without verifying **no event was published**, the service might still have published an event first and validated at a different step.

### No Automatic Deduplication

Spring's `ApplicationEventPublisher` is not responsible for dropping duplicate events by `eventId`. If the same occurrence is published twice, a simple listener may run twice. Duplicate tests can confirm that, and in business systems requiring deduplication, write **additional consumer/idempotency tests**, such as a unique `(consumerName,eventId)` constraint in the database.

## 12. Asynchronous Event Listeners Need a Different Testing Strategy

If a listener has:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Executes on another worker thread.
}
```

do not assert the listener finished right after `service.place(...)`. `ApplicationEventPublisher.publishEvent(...)` does not wait for `@Async` listeners to finish under the default contract.

**Important note on the recorder:** `@RecordApplicationEvents` records events within test scope and carries TestContext's thread/lifecycle constraints. For events emitted from worker pools—especially pre-created threads or threads lacking the test context—never assume every event re-emitted from a worker appears in the test's `ApplicationEvents`. Recording the initial event and async listener completion are **two separate questions**.

When asserting async listener outcomes, use a test-specific listener with `CountDownLatch`, `BlockingQueue`, `CompletableFuture`, or a thread-safe recorder with a timeout.

Completion-check pattern:

```java
if (!latch.await(5, TimeUnit.SECONDS)) {
    fail("Async listener did not finish");
}
assertEquals("ORD-42", capturedOrderId.get());
```

This is an integration snippet requiring `CountDownLatch`, `AtomicReference`, a configured executor, and a real listener. Use a timeout so the test fails helpfully if the job stalls; never use `Thread.sleep(100)` and read state as that causes flakiness.

### Testing Errors in Async Listeners

With `@Async void`, exceptions in a listener do not propagate back to the publisher thread. If a test must verify error handling, inspect the error handler, business state, or completion signal. Never treat `assertDoesNotThrow(service::place)` as proof an async listener succeeded.

### Executor-Backed Multicasters

If the application configures `SimpleApplicationEventMulticaster#setTaskExecutor(...)`, multiple listeners can be dispatched asynchronously. Test results are no longer guaranteed to finish in publish order as in synchronous execution. When checking multiple events, assert by **eventId/type and value sets**, rather than enforcing log order unless the contract requires it.

## 13. Testing @TransactionalEventListener

A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` listener handles events only when the publishing transaction commits; with `fallbackExecution=false` (the default), events emitted outside a transaction normally do not trigger this listener.

Common pitfall in tests:

```java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class OrderTransactionTests {
    // An @Transactional test rolls back by default at test end,
    // so an AFTER_COMMIT listener may not run.
}
```

This is a mechanism-illustrating excerpt, not a standalone runnable program.

To test post-commit execution accurately, you can:

- Call the real service with a transaction and **actually commit** via `TransactionTemplate` in an integration test.
- Within a test-managed transaction, call `TestTransaction.flagForCommit()` followed by `TestTransaction.end()` at an intentional point.
- Separate the assertion **event published before commit** from **AFTER_COMMIT listener finished after commit**.
- Also test rollback: an `AFTER_COMMIT` listener performs no side effects when the transaction rolls back.

### Do Not Confuse Event Recording with Post-Commit Processing

`ApplicationEvents` can record an event published inside a transaction, yet transaction-bound listeners run strictly per phase. Test the two goals with two separate assertions:

```text
1. Was OrderPlaced published?            -> check ApplicationEvents
2. Did after-commit handler run?         -> check post-commit effects
```

For post-commit callbacks writing new database records, consider `REQUIRES_NEW` and idempotency if business rules demand it. `AFTER_COMMIT` does not automatically provide exactly-once semantics, retries, or durability.

## 14. Mock the Publisher or Record Real Events?

Two complementary testing paths exist.

### 14.1. Unit Test with Mock ApplicationEventPublisher

In a unit test of a pure service, you can mock `ApplicationEventPublisher` (Mockito or hand-written fake) and use `ArgumentCaptor<OrderPlaced>` to inspect the object passed to `publishEvent`.

Benefits: fast, no Spring context needed, verifies the event constructed by the service matches its contract. Limitations: does not prove Spring registered listeners, matched generic payloads properly, or dispatched through the multicaster.

Conceptual example:

```java
verify(publisher).publishEvent(captor.capture());
OrderPlaced actual = captor.getValue();
// Assert properties on actual.
```

This is an integration-style Mockito snippet requiring defined mocks and captors; **not part of section 6's Maven suite**. When using `publishEvent(Object)` and `publishEvent(ApplicationEvent)` overloads, pay attention to argument types during `verify` so you do not match the wrong overload.

### 14.2. Integration Test Using @RecordApplicationEvents

Test real Spring behavior to:

- Invoke a service injected with Spring's publisher.
- Have Spring accept the POJO/record and dispatch through event infrastructure.
- Use `ApplicationEvents.stream(OrderPlaced.class)` to obtain actual payloads.
- Verify the record and corresponding listener receive the right type.

This is the approach implemented by section 6's program. It fits testing **payloads and properties** within Spring infrastructure, though if external systems exist, dedicated consumer/integration tests are still required.

### 14.3. Tests Should Not Know Too Many Implementation Details

Assert properties that genuinely belong to the business contract: `orderId`, `eventId`, `correlationId`, line-item values, and emission conditions. Do not assert:

- Callback order among listeners that have no explicit ordering requirement.
- Character-for-character thread names unless explicitly required.
- Raw timestamp numbers generated from `System.currentTimeMillis()`.
- The full `toString()` of a record when only a few fields matter.
- Total system event counts in the context when checking only one event type.

Tests tightly coupled to implementation details break easily on harmless refactors.

## 15. Rules for Versions, Enums, Currency, and Nulls

A quality payload usually enforces invariants deeper than "field is non-null":

| Data | Recommended Assertion | Risk If Omitted |
| --- | --- | --- |
| `schemaVersion` | Positive and matches the emitted version | Consumers parse the wrong schema |
| `aggregateVersion` | Matches post-change version | Out-of-order processing or overwriting read models |
| `status` enum | Equals expected business state | Event reports a false fact |
| `BigDecimal` | Value and scale/rounding policy explicit | Wrong monetary amount or broken equality |
| `currency` | Exact currency code if used by domain | Mixing currencies |
| `causationId` | Null or right parent ID per workflow | Lost causal relationship |
| `List/Map` | Exact nested data, unmodifiable | Races and corrupted snapshots |
| Nullable optional | Explicit null contract; `assertNull` when valid | NPE or invalid state |
| `eventId` | Unique per new occurrence, stable on retry | Faulty deduplication |
| Timestamps | Use `Clock.fixed` or fixture `Instant` | Clock-induced flaky tests |

For example, `schemaVersion=1` on `OrderPlaced` in the program is a valid value. If the schema evolves, test backward/forward compatibility per a concrete strategy; `@RecordApplicationEvents` does not automatically validate JSON formats sent over a broker.

Do not put secrets or unnecessary sensitive data into payloads just to simplify testing. A record generates a `toString()` containing all components, which could log raw values during debugging.

## 16. Common Testing Mistakes

1. **Asserting only listener invocation count.** It may run the right number of times with the wrong `orderId`/`eventId`.
2. **Calling the handler method directly instead of publishing through Spring** and claiming event infrastructure works.
3. **Forgetting `@RecordApplicationEvents`** yet attempting to inject and use `ApplicationEvents`.
4. **Injecting `ApplicationEvents` into a test constructor or singleton bean** instead of a test method/field.
5. **Using `events.stream().count()` to count one event type.** Other context events skew the test.
6. **Forgetting to filter by the POJO record class** and assuming only `ApplicationEvent` subclasses are recorded.
7. **Asserting only that the event is non-null** without checking metadata and nested data.
8. **Failing to copy input collections** and missing caller mutation of the list after publish.
9. **Assuming a record is deeply immutable** despite holding mutable arrays/entities.
10. **Asserting `Instant.now()` equals `Instant.now()`.** Nearby timestamps are not guaranteed equal.
11. **Comparing `BigDecimal` with `equals` without considering scale.** Equality rules must match domain semantics.
12. **Not isolating tests sharing a cached ApplicationContext.** Singleton listeners retain data from prior tests.
13. **Guessing completion order when listeners use `@Async`.** Use latches/futures with timeouts.
14. **Assuming `@RecordApplicationEvents` captures every event from every worker thread** regardless of thread/context propagation; verify limits and instrumentation.
15. **Forgetting test transactions roll back by default.** `AFTER_COMMIT` listeners do not run merely because the publisher emitted an event.
16. **Treating `getSource()` as business `causationId`.** Spring's source object and parent-event causality are two distinct concepts.
17. **Assuming Spring auto-deduplicates `eventId`.** The same event can be emitted multiple times; idempotency belongs to consumer design.
18. **Using fixed `Thread.sleep` to test async.** Easily flakes on slow CI machines.
19. **Only mocking the publisher without testing a real Spring path.** Unit tests do not replace wiring integration tests.
20. **Treating recorded events as successful email delivery or DB commit.** Publishing does not guarantee side effects or durability.

## 17. Pre-Completion Test Suite Checklist

- [ ] Identified the exact **event type** and real publication point.
- [ ] Tests use `@SpringJUnitConfig`/`@RecordApplicationEvents` or a valid recorder.
- [ ] Payloads are retrieved via `ApplicationEvents.stream(PayloadType.class)`.
- [ ] Concrete assertions verify count, IDs, metadata, timestamps, and nested data.
- [ ] Domain timestamps are controlled via fixtures or an injectable `Clock`.
- [ ] Validation errors cause **no event to be published**.
- [ ] Other event types are not miscounted.
- [ ] Payload snapshots remain unchanged after the caller mutates input collections.
- [ ] Mutation via accessors is verified to be rejected when the contract requires immutability.
- [ ] If using an `ApplicationEvent` subclass, `source` and `timestamp` are checked meaningfully.
- [ ] No assumption that Spring automatically drops duplicate events.
- [ ] Recorders/listeners sharing a context are reset; tests do not depend on preceding test methods.
- [ ] If async, timeout-bounded wait mechanisms and thread-safe recorders are used.
- [ ] If post-commit, commit/rollback and post-commit effects are tested explicitly.
- [ ] External side effects have dedicated tests with retries and idempotency when required.
- [ ] `mvn test` runs all tests and CI reports zero failures/errors.

**Conclusion:** Testing Spring Application Events should treat events as **a data contract**: right type, right emission count, right payload and metadata, deterministic across time, and published through Spring's real path. `@RecordApplicationEvents` + `ApplicationEvents.stream(Class<T>)` let you capture and assert events directly in Spring TestContext; JUnit 5 provides the assertions; testing async listeners, transactions, and side effects requires dedicated verification mechanisms.

## Official Documentation

- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — ApplicationEvents API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — Spring JUnit Jupiter annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
