# Asserting Events with Streams in Spring Application Events Testing

## 1. Goal: Verifying That Events Were Truly Published

In Spring Framework, a service typically does not directly return the domain events it emits:

```java
public void placeOrder(String orderId) {
    // Perform valid business operation.
    publisher.publishEvent(new OrderPlaced(orderId, 2500));
}
```

The snippet above is an illustrative method: assuming `publisher` is an `ApplicationEventPublisher`, `OrderPlaced` is an application-defined event type, and business validation has already been performed. To test behavior, asserting only the return value is insufficient. We need to know:

- Was the **right event type** published?
- How many times was it published, and were there duplicates?
- Does the payload have the right identifiers and business values?
- With invalid input, was no success event **emitted**?
- If multiple events of the same type are emitted, how can we filter, transform, and compare against expected lists?

Spring TestContext Framework provides `org.springframework.test.context.event.ApplicationEvents` to record application events within the scope of **a single test method**. This API exposes recorded events as a `java.util.stream.Stream`, very convenient for assertions with JUnit 5 or AssertJ.

Conceptual example:

```java
long count = events.stream(OrderPlaced.class).count();
assertEquals(1, count);
```

Distinguish right from the start: **this is a capability of Spring TestContext (`spring-test` module), not syntax exclusive to Spring Boot**. A plain Spring Framework project can use `@RecordApplicationEvents` + `@SpringJUnitConfig`; Spring Boot projects typically use `@SpringBootTest` with this recording annotation.

## 2. APIs to Know: ApplicationEvents and @RecordApplicationEvents

The primary testing toolkit consists of:

| Component | Package | Purpose |
| --- | --- | --- |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Requests Spring TestContext to record application events in each test |
| `ApplicationEvents` | `org.springframework.test.context.event` | Provides recorded events for the currently running test |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Integrates recording with the test lifecycle; registered by default in standard TestContext configurations |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Combines `SpringExtension` and `ContextConfiguration` for JUnit Jupiter |
| `ApplicationEventPublisher` | `org.springframework.context` | Object used by application services to publish |
| `Stream<T>` | `java.util.stream` | Filters, counts, transforms, and searches events for assertions |

Core `ApplicationEvents` operations in Spring Framework 6.2:

```java
Stream<ApplicationEvent> all = events.stream();

Stream<OrderPlaced> placed = events.stream(OrderPlaced.class);

events.clear();
```

The snippet above illustrates the API only, assuming `events` is supplied in the test and `OrderPlaced` is declared by the application. `ApplicationEvents.stream(Class<T>)` can stream both **`ApplicationEvent` subclasses** and **event payloads** of the specified type. This matters because `ApplicationEventPublisher.publishEvent(Object)` supports POJOs/Java records that do not extend `ApplicationEvent`.

`ApplicationEvents.clear()` erases **events recorded in the test's recorder**; it does not revoke events already sent to listeners, undo side effects, roll back transactions, or delete domain data.

### 2.1. Why Is @RecordApplicationEvents Required?

Registering a business listener via `@EventListener` does not create a test recorder automatically. You must enable it explicitly:

```java
@SpringJUnitConfig(MyConfig.class)
@RecordApplicationEvents
class OrderServiceTest {
    // Test methods...
}
```

If you forget `@RecordApplicationEvents`, the test is not guaranteed to receive `ApplicationEvents` for injection through the standard flow. Do not attempt `new ApplicationEvents()`: it is an interface supplied by TestContext, not an event-storing object instantiated by the application.

### 2.2. How to Inject ApplicationEvents?

The approach guided by Spring when using JUnit Jupiter is injecting it into a **method parameter**:

```java
@Test
void publishesEvent(ApplicationEvents events) {
    // events is used strictly within this test method.
}
```

Once the test has `@SpringJUnitConfig` or `@SpringBootTest` along with `@RecordApplicationEvents`, `SpringExtension` can supply this argument.

You can also inject into a field:

```java
@Autowired
ApplicationEvents events;
```

However, **do not constructor-inject ApplicationEvents into the test class**. It is registered as a resolvable dependency scoped to the test method lifecycle, not a singleton application bean available everywhere.

### 2.3. Does TestExecutionListener Need Manual Registration?

With standard Spring TestContext configuration, `ApplicationEventsTestExecutionListener` is registered by default. You only need to review this if the project configures `@TestExecutionListeners` itself and replaces the default listener list.

If you replace the list and drop the listener managing application events, `@RecordApplicationEvents` may not work as expected. Do not add duplicate listeners arbitrarily; inspect how existing configuration merges.

## 3. Two Different Streams: stream() and stream(Class<T>)

### 3.1. stream(Class<T>) — The Most Common Path

```java
events.stream(OrderPlaced.class)
```

The stream element type is `OrderPlaced`. If `OrderPlaced` is a Java record and the publisher calls `publishEvent(new OrderPlaced(...))`, Spring still captures the corresponding **payload** for the typed stream to return.

Because it is typed, you can call accessors directly:

```java
boolean found = events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100"));
```

No casting from `ApplicationEvent` or manual `instanceof` checks needed.

### 3.2. stream() — Stream of Application Event Wrappers

```java
Stream<ApplicationEvent> eventsOnContext = events.stream();
```

Here the element type is `ApplicationEvent`. When you publish a POJO, Spring can wrap it in `PayloadApplicationEvent<?>` for delivery through the `ApplicationEvent` infrastructure. Therefore, the following check can yield the wrong result even when the POJO was emitted:

```java
// Counterexample: stream() contains ApplicationEvent,
// not necessarily POJO records directly.
boolean found = events.stream()
        .anyMatch(e -> e instanceof OrderPlaced);
```

It also has a Java typing problem: if `OrderPlaced` does not extend `ApplicationEvent`, `instanceof OrderPlaced` on a variable of type `ApplicationEvent` may **fail to compile** when the two types are incompatible under Java's type-checking rules. Use `events.stream(OrderPlaced.class)` instead.

When handling a mix of multiple event types, you can use `stream()` and check `PayloadApplicationEvent<?>` with `getPayload()`, though you should do so only if the test truly needs to observe **the entire event stream**. For one concrete domain event type, the typed stream is simpler and more accurate.

### 3.3. Watch Out for Lifecycle Events and Framework Events

`ApplicationContext` can emit other events like `ContextRefreshedEvent` and `ContextClosedEvent`; Spring TestContext also emits test lifecycle events. When asserting a total count via `events.stream().count()`, you can accidentally count events unrelated to the behavior under test.

**Avoid:**

```java
assertEquals(1, events.stream().count());
```

when the goal is proving the service published exactly one `OrderPlaced`.

**Prefer:**

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

Only compare the total of all events if you have explicitly bounded the scope and framework event types that can appear in that test.

## 4. Common Stream API Operations for Assertions

| Operation | Pattern | When to Use |
| --- | --- | --- |
| `count()` | `stream(OrderPlaced.class).count()` | Counting a specific event type |
| `anyMatch(...)` | Finding an event with a specific `orderId` | Confirming at least one matching fact exists |
| `noneMatch(...)` | No event violates a rule | Confirming something was **not** emitted |
| `allMatch(...)` | Every event satisfies a predicate | Checking general invariants |
| `filter(...)` | Filtering by tenant/order/status | Narrowing the event set before assertions |
| `map(...)` | Mapping events to IDs/amounts | Concise payload comparisons |
| `findFirst()` | Getting the first event in encounter order | When a matching event is expected and order is deterministic |
| `toList()` | Materializing event/payload list | Comparing lists, repetition counts, and order |
| `distinct()` | Removing duplicate values | Useful for analysis, **never** to hide duplicates |
| `groupingBy(...)` | Grouping by tenant/type | When summarizing multiple occurrences |

Example for counting exactly once:

```java
assertEquals(1L, events.stream(OrderPlaced.class).count());
```

To verify a specific payload:

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100")
                && e.amountMinor() == 2500));
```

To verify no "order placed" event when rejected:

```java
assertEquals(0L, events.stream(OrderPlaced.class).count());
assertTrue(events.stream(OrderRejected.class)
        .anyMatch(e -> e.reason().equals("INVALID_AMOUNT")));
```

To verify all events contain valid data:

```java
assertTrue(events.stream(OrderPlaced.class)
        .allMatch(e -> e.amountMinor() > 0));
```

**Trap:** `allMatch` on an **empty stream returns true** (vacuous truth). If the goal is "at least one event exists, and all events are valid," assert `count > 0` or non-empty list first.

### 4.1. Count First, Then Inspect Contents

An assertion with only `anyMatch` can pass even if the service emits **two or three duplicate events**. When business logic requires exactly one *occurrence during the test call*, combine:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("O-100", placed.get(0).orderId());
assertEquals(2500, placed.get(0).amountMinor());
```

This checks **count and payload** together and reads more clearly than a complex predicate chain.

Note that "one event in the test" does not mean the platform guarantees **exactly-once delivery** across brokers or processes. This is strictly an assertion at a controlled test boundary.

### 4.2. Comparing the Order of Multiple Same-Type Events

```java
List<String> ids = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .toList();

assertEquals(List.of("O-100", "O-101"), ids);
```

This makes sense when publishing runs **synchronously in a deterministic order**, and you want to verify the order recorded by the recorder. Do not infer from it that asynchronous listeners or remote consumers completed in that order.

## 5. Runnable Java 17 Project Example: Spring Framework + JUnit 5

The following example is a small **integration-style test** of `ApplicationEventPublisher`, requiring no Spring Boot, HTTP server, or database. It uses:

- Java 17 or newer.
- Spring Framework `spring-context` and `spring-test` version **6.2.12**.
- JUnit Jupiter **5.11.4**.
- Maven Surefire to execute `@Test` methods.
- Java records as domain event payloads.

### 5.1. Project Structure

```text
spring-event-stream-test/
├── pom.xml
└── src/test/java/demo/EventStreamTest.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-stream-test</artifactId>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/test/java/demo/EventStreamTest.java`:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(EventStreamTest.Config.class)
@RecordApplicationEvents
class EventStreamTest {

    record OrderPlaced(String orderId, int amountMinor) {}
    record OrderRejected(String orderId, String reason) {}

    static final class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void place(String orderId, int amountMinor) {
            Objects.requireNonNull(orderId, "orderId");

            if (amountMinor <= 0) {
                publisher.publishEvent(
                        new OrderRejected(orderId, "INVALID_AMOUNT"));
                return;
            }

            publisher.publishEvent(
                    new OrderPlaced(orderId, amountMinor));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Autowired
    OrderService service;

    @Test
    void recordsOneEventWithCorrectPayload(ApplicationEvents events) {
        events.clear();
        service.place("O-100", 2500);

        List<OrderPlaced> placed =
                events.stream(OrderPlaced.class).toList();

        assertEquals(1, placed.size());
        assertEquals("O-100", placed.get(0).orderId());
        assertEquals(2500, placed.get(0).amountMinor());
        assertEquals(0L, events.stream(OrderRejected.class).count());
    }

    @Test
    void filtersSeveralEventsByType(ApplicationEvents events) {
        events.clear();
        service.place("O-101", 1200);
        service.place("O-BAD", 0);
        service.place("O-102", 3400);

        assertEquals(2L, events.stream(OrderPlaced.class).count());
        assertEquals(1L, events.stream(OrderRejected.class).count());

        List<String> ids = events.stream(OrderPlaced.class)
                .map(OrderPlaced::orderId)
                .toList();
        assertEquals(List.of("O-101", "O-102"), ids);
    }

    @Test
    void rejectsInvalidAmountWithoutPlacedEvent(ApplicationEvents events) {
        events.clear();
        service.place("O-103", -1);

        assertEquals(0L, events.stream(OrderPlaced.class).count());
        assertTrue(events.stream(OrderRejected.class)
                .anyMatch(e -> e.orderId().equals("O-103")
                        && e.reason().equals("INVALID_AMOUNT")));
    }

    @Test
    void checksAllEventsAndExactMultiplicity(ApplicationEvents events) {
        events.clear();
        service.place("O-104", 500);
        service.place("O-104", 600);

        List<OrderPlaced> placed =
                events.stream(OrderPlaced.class).toList();

        assertEquals(2, placed.size());
        assertTrue(placed.stream().allMatch(e -> e.amountMinor() > 0));
        assertEquals(List.of(500, 600),
                placed.stream().map(OrderPlaced::amountMinor).toList());
    }

    @Test
    void clearResetsOnlyTheRecordedWindow(ApplicationEvents events) {
        events.clear();
        service.place("O-OLD", 100);
        assertEquals(1L, events.stream(OrderPlaced.class).count());

        events.clear();
        service.place("O-NEW", 200);

        List<String> ids = events.stream(OrderPlaced.class)
                .map(OrderPlaced::orderId).toList();
        assertEquals(List.of("O-NEW"), ids);
        assertFalse(ids.contains("O-OLD"));
    }

    @Test
    void noCallMeansNoBusinessEvent(ApplicationEvents events) {
        events.clear();

        assertEquals(0L, events.stream(OrderPlaced.class).count());
        assertEquals(0L, events.stream(OrderRejected.class).count());
    }
}
```

From the `spring-event-stream-test` directory, run:

```bash
mvn test
```

When JDK 17+, Maven, and dependency downloads are available, all **6 test methods** in `EventStreamTest` should pass. The Maven Surefire summary will be equivalent to:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

These are the core expected outcome lines; dependency download lines, Maven/Surefire messages, and log paths may vary by environment. This demo does not print business stdout because the goal is **test assertions**.

### 5.2. Why Does This Configuration Work?

- `@SpringJUnitConfig(EventStreamTest.Config.class)` integrates JUnit Jupiter with Spring TestContext and loads a tiny configuration.
- `@Bean OrderService` receives `ApplicationEventPublisher` from the Spring context. The `@Autowired OrderService service` test field obtains the real bean.
- `@RecordApplicationEvents` activates the recorder for each test method's lifecycle.
- The `ApplicationEvents events` parameter on each `@Test` is supplied by `SpringExtension` for the current test scope.
- `events.clear()` establishes a clean recording window **before the operation under test**. It does not affect context beans; it only clears previously recorded events in the recorder.
- When `service.place(...)` is called, the service publishes an `OrderPlaced` or `OrderRejected` Java record object. Spring's event framework allows publishing POJOs, and the typed recorder stream returns payloads of the right type.
- Each test asserts only events from the operations it actually invoked, without depending on the number of `ContextRefreshedEvent`s or test-lifecycle framework events.

### 5.3. Why Is No @EventListener Needed in the Example?

This lesson tests **whether the producer publishes the right event**, not consumer side effects. `ApplicationEvents` records events emitted inside the test's application context, so declaring a business `@EventListener` is unnecessary for assertions to have data.

Testing whether a listener sends an email, updates a table, or calls an external service is **a separate test objective**. The recorder seeing an event only proves the fact was emitted at the Spring context boundary; it does not prove a consumer successfully processed every side effect.

### 5.4. Note on Example Consistency

The `OrderService` example is intentionally simple: no repository, no transaction storage, no duplicate checks. `checksAllEventsAndExactMultiplicity` proves **two `place` calls produce two events**, not that this is the right business behavior for a real sales system.

In production, emit `OrderPlaced` only after the domain confirms valid state. Tests should pair that with invariant assertions and verify events are **not** emitted when operations are rejected.

## 6. Useful Assertions in Real-World Projects

### 6.1. Asserting Event Existence

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> "O-100".equals(e.orderId())));
```

Good when a test only needs to prove a specific fact appeared. However, if the system must not emit duplicates, add a count check.

### 6.2. Asserting Forbidden Events Are Absent

```java
assertTrue(events.stream(OrderPlaced.class)
        .noneMatch(e -> "O-FAILED".equals(e.orderId())));
```

This avoids coupling to unrelated same-type event contents, especially when a test intentionally executes multiple operations in one workflow.

### 6.3. Asserting the Exact Set of Events

```java
List<String> actualIds = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .toList();

assertEquals(List.of("O-1", "O-2"), actualIds);
```

This check makes sense when publish order is deterministic by design. If only an unordered set is needed, use `Set.copyOf(actualIds)` together with an assertion on **element count first** to avoid silently deduplicating. Never call `distinct()` and then conclude there were no duplicates.

### 6.4. Asserting Accurate Monetary and Tenant Values

With payload:

```java
public record PaymentCaptured(
        String tenantId,
        String paymentId,
        long amountMinor,
        String currency) {}
```

You can write:

```java
List<PaymentCaptured> payments =
        events.stream(PaymentCaptured.class).toList();

assertEquals(1, payments.size());
assertEquals("tenant-blue", payments.get(0).tenantId());
assertEquals("P-3", payments.get(0).paymentId());
assertEquals(125000L, payments.get(0).amountMinor());
assertEquals("VND", payments.get(0).currency());
```

These snippets are **illustrations for a separate test with `PaymentCaptured`**, not part of the Maven project in section 5. Assert domain-meaningful values rather than full runtime objects or nondeterministic timestamps.

### 6.5. Asserting with AssertJ When Already Used by the Project

```java
import static org.assertj.core.api.Assertions.assertThat;

List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertThat(placed)
        .hasSize(2)
        .extracting(OrderPlaced::orderId)
        .containsExactly("O-1", "O-2");
```

This snippet assumes **AssertJ** is on the test classpath. Section 5's Maven example uses only JUnit Jupiter and **does not** include AssertJ as a dependency, so the AssertJ snippet does not belong to that standalone program.

With AssertJ, `assertThat(events.stream(OrderPlaced.class))` may also work depending on API version; yet materializing with `toList()` usually yields clearer error messages, multi-attribute checks, and easier debugging.

### 6.6. Asserting Nested Payloads with Controlled Predicates

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100")
                && e.amountMinor() > 0));
```

Predicates should be short and side-effect-free. With many attributes, extract into a `List<Event>` and assert individual fields for clearer diagnostics when a test fails.

## 7. Remember That Stream Is a Single-Use Pipeline

A Java `Stream` is not a reusable collection. Common mistake:

```java
Stream<OrderPlaced> stream = events.stream(OrderPlaced.class);

long count = stream.count();
boolean found = stream.anyMatch(e -> e.orderId().equals("O-1"));
// Wrong: stream has already been consumed. Can throw IllegalStateException.
```

First correct approach: create a **fresh stream** for each terminal operation:

```java
long count = events.stream(OrderPlaced.class).count();
boolean found = events.stream(OrderPlaced.class)
        .anyMatch(e -> "O-1".equals(e.orderId()));
```

Second correct approach: materialize into a **List** once:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("O-1", placed.get(0).orderId());
```

With `Stream.toList()` since Java 16+, the returned list is unmodifiable. Do not call `placed.add(...)` on it to simulate new events. If you need a mutable list for another test setup, intentionally wrap it with `new ArrayList<>(...)`.

### Streams Have Lazy Evaluation

`filter/map` operations generally do not run until a terminal operation like `count`, `toList`, or `anyMatch` is called. Never put state-mutating logic or side effects inside predicates, as the compiler and `Stream` do not guarantee traversing all elements when short-circuiting operations like `anyMatch`/`findFirst` are used.

Good example:

```java
List<String> ids = events.stream(OrderPlaced.class)
        .filter(e -> e.amountMinor() > 0)
        .map(OrderPlaced::orderId)
        .toList();
```

Do not call `publishEvent` inside `filter` to "produce extra events to test"; mutating the source collection while a stream is being consumed can lead to unpredictable results.

## 8. Isolation: Each Test Needs a Clear Recording Window

### 8.1. @RecordApplicationEvents Is Scoped per Test Method

According to Spring TestContext, `ApplicationEvents` applies to **the lifecycle of the currently executing test method**, not the entire application's history. This reduces cross-test data interference.

Even so, events from the test lifecycle or a setup routine can be recorded. If the goal is checking a single command, a clear pattern is calling `events.clear()` right before the action:

```java
events.clear();
service.place("O-100", 2500);
assertEquals(1, events.stream(OrderPlaced.class).count());
```

When using `@BeforeEach` to seed data that emits domain events, remember those setup events do not belong to the action under test. Clear after setup or organize fixtures so they do not publish.

### 8.2. clear Does Not Reset the Application

`events.clear()` only clears the recorder. It does **not**:
- Undo a committed transaction.
- Unregister listeners in the context.
- Reset state of singleton services/repositories.
- Cancel running async tasks.
- Delete messages already sent to queues or brokers.
- Erase audit records written to a database.

If tests need isolated data, use transaction rollbacks where appropriate, independent test data, repository cleanup, or Spring context isolation. Never abuse `@DirtiesContext` merely to wipe the recorder.

### 8.3. Do Not Inject ApplicationEvents into the Test Constructor

`ApplicationEvents` is a dependency scoped to the test method's lifecycle. Therefore:

```java
// Do not use in the test class constructor:
MyTest(ApplicationEvents events) {
    this.events = events;
}
```

This is a **counterexample**, not compilable code. Use injection into a `@Test` method or a field.

### 8.4. Custom TestExecutionListeners

If a project defines a custom `@TestExecutionListeners(listeners = {...})` without merging defaults, the needed recorder may be omitted. Read Spring TestContext's `TestExecutionListeners` configuration rules before replacing default listeners, instead of manually creating an `ApplicationEvents` in test code.

## 9. When Do count, anyMatch, and allMatch Give Misleading Results?

### 9.1. allMatch on an Empty Stream

```java
assertTrue(events.stream(OrderPlaced.class)
        .allMatch(e -> e.amountMinor() > 0));
```

If zero events exist, the assertion still passes. To test "at least one event exists and all have positive amounts," write:

```java
List<OrderPlaced> placed = events.stream(OrderPlaced.class).toList();
assertFalse(placed.isEmpty());
assertTrue(placed.stream().allMatch(e -> e.amountMinor() > 0));
```

### 9.2. anyMatch Does Not Catch Duplicates

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-1")));
```

It passes even if 10 `OrderPlaced("O-1",...)` events exist. If exactly one occurrence is required:

```java
long matching = events.stream(OrderPlaced.class)
        .filter(e -> e.orderId().equals("O-1"))
        .count();
assertEquals(1L, matching);
```

### 9.3. Asserting "No Event Emitted" on the Full Stream

```java
assertEquals(0, events.stream().count());
```

This breaks easily due to other Spring or fixture events. To verify "a rejected operation emits no success event," write:

```java
assertEquals(0L, events.stream(OrderPlaced.class).count());
```

### 9.4. distinct() Hides Evidence of Duplicate Publishing

```java
long unique = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .distinct()
        .count();
```

`unique == 1` does not prove it was published only once. Count raw events **before** calling `distinct()`.

### 9.5. Using findFirst Without Checking Empty

```java
OrderPlaced first = events.stream(OrderPlaced.class)
        .findFirst()
        .orElseThrow(() ->
                new AssertionError("Expected an OrderPlaced event"));
```

In a test where no event might arrive, this produces a clear assertion failure. Never call `.get()` on `Optional.empty()` without knowing an element exists.

## 10. Asserting Order: Be Explicit About Order of What

There are at least three distinct concepts:

1. **Publish order:** the service calls `publishEvent(A)` then `publishEvent(B)`.
2. **Recorder capture order:** events received by the recorder in the test context.
3. **Consumer completion order:** listeners finish handling A then B, which can differ entirely when async.

With synchronous code as in the example, `events.stream(OrderPlaced.class).map(...).toList()` is a sensible way to verify the order of **recorded occurrences of the same type**.

To verify a workflow emits different event types in order, use recorded events from the general stream **with wrapper handling** or a dedicated test recorder capturing metadata/types by design. Do not compare `List<Class<?>>` via `events.stream().map(Object::getClass)` expecting `OrderPlaced.class`: for POJOs, elements can be `PayloadApplicationEvent` wrappers.

An option for inspecting event payloads in `stream()` when truly necessary:

```java
List<Object> payloads = events.stream()
        .filter(e -> e instanceof PayloadApplicationEvent<?>)
        .map(e -> ((PayloadApplicationEvent<?>) e).getPayload())
        .toList();
```

This is an **illustrative snippet** requiring imports for `org.springframework.context.PayloadApplicationEvent` and `List`. It is not in section 5's `EventStreamTest.java`. Avoid this snippet if a test cares about only one type, since the typed stream is shorter and stronger.

Important: checking recorded order in a test creates no guarantee about **message broker ordering**, transaction commits, or task completion in an executor.

## 11. Synchronous vs. Asynchronous Events: Recorder Limitations

### 11.1. When Publishing Synchronously

`SimpleApplicationEventMulticaster` runs listeners on the publisher's thread by default. In the example test, `service.place(...)` finishes before reading `events.stream(...)`; therefore assertions need no waiting and results are deterministic.

The synchronous case is where `@RecordApplicationEvents` is most convenient.

### 11.2. When Listeners Run Asynchronously

Two situations must be distinguished:

- **Synchronous publish, `@Async` listener:** the event may already be recorded on the publishing thread, while the consumer runs side effects on another thread and has not finished yet. Asserting "event was published" remains different from asserting "listener finished work."
- **Event published from another worker thread:** Spring TestContext uses test/thread-scoped event management. Do not assume `ApplicationEvents` accurately captures every event emitted from off-test threads regardless of timing or technique. Test the real system and use an appropriate recorder/thread-safe test probe.

Do not apply "publish → immediately `count()` → assert" to an async pipeline without controlling recording boundaries. If the system under test actually publishes after a `CompletableFuture`, queue, or scheduler, you need a bounded wait mechanism and a recorder observing where the event is emitted.

### 11.3. Do Not Use Thread.sleep Instead of Completion Conditions

Unstable pattern:

```java
service.startAsync();
Thread.sleep(100);
assertEquals(1L, events.stream(OrderPlaced.class).count());
```

Thread scheduling, CI load, and GC make 100 ms unreliable. Instead:

- Use a `CountDownLatch` or `CompletableFuture` controlled by the test with a timeout.
- Use Awaitility if already in project dependencies and the recorder truly captures cross-thread events.
- When testing the **producer**, isolate publishing in a synchronous unit and test async side effects separately.
- Design probe listeners with a `BlockingQueue` or concurrent collection when multiple threads may invoke them.

Simple probe example for **one event type**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;

public class EventProbe {
    private final BlockingQueue<OrderPlaced> received =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        received.add(event);
    }

    public OrderPlaced awaitOne() throws InterruptedException {
        return received.poll(3, TimeUnit.SECONDS);
    }
}
```

This is an **illustrative test helper**, assuming `OrderPlaced` is declared and the class is registered as a Spring bean. Tests can assert `assertNotNull(probe.awaitOne())` after invoking the async operation. However, it measures **that `EventProbe`'s listener was invoked**, not that another business listener completed. To verify consumer side effects, synchronize at the boundary where side effects execute.

## 12. Transactional Events: Assert at the Right Time

`@TransactionalEventListener` typically executes by transaction phase, such as `AFTER_COMMIT`. `ApplicationEvents` recording a published event does **not** prove the post-commit callback ran:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Logic executed after successful transaction commit.
}
```

This is an **illustrative method snippet** requiring Spring beans, a transaction manager, and corresponding imports.

Common scenario:

1. Service starts a transaction and publishes `OrderPlaced`.
2. Recorder captures publication in the test.
3. Transaction **rolls back** before commit.
4. `AFTER_COMMIT` callback does not run; yet an "event was published" assertion can still pass.

In particular, `@Transactional` tests normally roll back when the test ends, so `@TransactionalEventListener(AFTER_COMMIT)` will not necessarily run. To test post-commit execution, use explicit transaction boundaries, `TestTransaction`, or intentional commit strategies, and verify side effects rather than only counting events.

**Rule:** `events.stream(OrderPlaced.class).count()` verifies **the publish path into `ApplicationContext`** within test scope. It does not verify that a database transaction committed, a message broker received it, or an `AFTER_COMMIT` callback finished.

If events must be delivered durably across processes, combine appropriate outbox/retry/delivery tests; never use stream recording to claim exactly-once semantics.

## 13. When Should You Use Mockito Instead of ApplicationEvents Stream?

The two techniques have slightly different goals:

| Option | What Is Verified | Best Suited For |
| --- | --- | --- |
| Mock `ApplicationEventPublisher` with Mockito | `publishEvent(...)` was called with the right argument | Pure unit tests without a Spring Context |
| `@RecordApplicationEvents` + `ApplicationEvents.stream(...)` | Event published through a real application context in Spring TestContext | Integration/slice tests using a context |
| Business listener recorder | Listener actually received the event and can record the payload | Dispatch/listener behavior tests |
| Checking repository/outbox/broker | Durable state/delivery | Transaction/integration/contract tests |

Illustrative Mockito unit test:

```java
ApplicationEventPublisher publisher =
        mock(ApplicationEventPublisher.class);

OrderService service = new OrderService(publisher);
service.place("O-100", 2500);

verify(publisher).publishEvent(
        new OrderPlaced("O-100", 2500));
```

This is an **illustrative snippet**, requiring Mockito test dependencies/imports and access to `OrderService`'s constructor and `OrderPlaced` record. If the publisher has overloads or other call paths, target the exact overload. Records have value equality, so a new event object with equal fields matches `verify` by `equals()`.

Do not spin up Spring TestContext for a unit test merely proving a collaborator method was called. Conversely, when testing integration event routing, `ApplicationEvents` reflects the publish path through Spring context better than mocking the interface alone.

### Trap When Testing Before the Publication Boundary

A mock proves the service **called the publisher**, not that the context actually dispatched the event. The test-context recorder proves the event entered the publish infrastructure, not durable delivery. Pick the tool for the target rather than assuming one replaces all others.

## 14. Testing Events with Nondeterministic Payloads Like UUID or Instant

Many events carry a randomly generated `eventId` and an `occurredAt` from the current clock. Asserting the entire object against a fixed literal can make tests brittle.

Example domain payload:

```java
public record OrderPlaced(
        UUID eventId,
        String orderId,
        Instant occurredAt) {}
```

Appropriate assertion pattern:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
OrderPlaced event = placed.get(0);

assertEquals("O-100", event.orderId());
assertNotNull(event.eventId());
assertNotNull(event.occurredAt());
```

This is a logically standalone snippet assuming the test uses the matching 3-field `OrderPlaced`, distinct from the 2-field record in section 5; requires JUnit, `UUID`, and `Instant` imports.

If you need to assert an **exact** timestamp, inject `Clock.fixed(...)` into the service so tests have deterministic time. Avoid comparing `Instant.now()` against an estimated value and loosening tolerances arbitrarily.

If an event holds a mutable `List` or `Map` inside its payload, ensure snapshots and defensive copies by design; stream payload assertions can be affected if the producer mutates the object after publishing.

## 15. Negative Assertions Are Essential

For business-grade tests, ask not only "which event was emitted?", but also **"which event must strictly never be emitted on this branch?"**

For example:

| Scenario | Required Event | Forbidden Event |
| --- | --- | --- |
| Valid order placement | `OrderPlaced` | `OrderRejected` |
| Invalid amount | `OrderRejected` | `OrderPlaced` |
| Payment pending | May emit `PaymentPending` per domain | Never emit `PaymentCaptured` before capture |
| Rolled-back transaction | May have internal pre-commit event per design | Never claim a durable integration event was delivered |
| Unauthorized user | May log a denied audit event per policy | Never emit a business success fact |
| Blocked duplicate command | May emit a dedicated idempotency result | Never emit another business fact if it did not happen |

Combining positive and negative assertions catches bugs like "emitting both `OrderPlaced` and `OrderRejected` for the same command." Asserting only that one event exists can let that bug slip through.

## 16. Common Mistakes

1. **Forgetting `@RecordApplicationEvents`** and assuming the recorder is automatically present in every Spring test.
2. **Confusing `org.springframework.boot.context.event.*`** with `ApplicationEvents`: the recorder API belongs to `spring-test`, not Spring Boot startup event packages.
3. **Using `events.stream()` and assuming elements are Java record payloads**: it returns `ApplicationEvent` wrappers; use `stream(MyEvent.class)`.
4. **Counting total events** to prove a domain event: lifecycle/test-framework events can interleave.
5. **Using only `anyMatch` while forgetting count**: duplicate events still pass.
6. **Using only `allMatch` while forgetting non-empty checks**: an empty stream causes a false pass.
7. **Reusing the same `Stream`** after `count()` then `anyMatch()`: throws an exception or breaks test structure.
8. **Calling `clear()` after the action and before assertions**: accidentally erases the evidence to verify.
9. **Believing `clear()` rolls back data**: it only clears the recorder in test scope.
10. **Constructor-injecting ApplicationEvents**: the dependency is scoped per test method and unsuitable for test constructor injection.
11. **Using custom `@TestExecutionListeners` that drop defaults**: the recorder is not registered properly.
12. **Asserting async completion order via recorder order**: those are two different orders.
13. **Using `Thread.sleep(100)` to wait for events**: tests flake when CI is slow.
14. **Treating the event recorder as proof of listener side-effect success**: the recorder checks publication, not consequences.
15. **Treating the event recorder as proof of transaction commit**: publication can occur prior to rollback.
16. **Confusing TestContext event recording with broker delivery guarantees**: there is no automatic durability, retry, or exactly-once guarantee.
17. **Abusing `distinct()`** and overlooking duplicate-emission bugs.
18. **Comparing runtime UUIDs/timestamps to fixed literals** without injecting a fixed clock.
19. **Not testing unauthorized/invalid branches**: success events may be emitted erroneously.
20. **Sharing test state across methods**: outcomes depend on test order or side-effecting singletons.

## 17. Checklist Before Declaring a Test PASS

- [ ] Have you separated **producer publication** from **consumer completion**?
- [ ] Does the test use Spring TestContext and `@RecordApplicationEvents`, or is it a pure unit test?
- [ ] Is `ApplicationEvents` injected via a method/field rather than the constructor?
- [ ] Are you using `events.stream(MyEvent.class)` to get the right payload type?
- [ ] Have you established a clean recording window with `clear()` when needed?
- [ ] Are you asserting **exact counts**, not just `anyMatch`?
- [ ] Are you asserting business-meaningful fields and key invariants?
- [ ] Do invalid/unauthorized branches verify **no success event is emitted**?
- [ ] Have you avoided `allMatch` on an empty stream as proof of existence?
- [ ] When checking order, is it clearly publish/recording order rather than listener completion?
- [ ] Are `spring-test`, JUnit Jupiter, and `TestExecutionListener` dependencies configured properly?
- [ ] If async, are you using a proper wait mechanism and thread-safe recorder?
- [ ] If transactional, have you separated publication assertions from after-commit/durability assertions?
- [ ] If payloads contain timestamps/UUIDs, does the test use deterministic inputs or suitable assertions?
- [ ] Are business events from setup or other tests prevented from polluting results?
- [ ] When the test fails, are assertion messages clear enough to pinpoint wrong event type, count, or payload?

**Conclusion:** `ApplicationEvents.stream(Class<T>)` combined with `@RecordApplicationEvents` is a direct, readable way to assert domain events published by a Spring application context within test method scope. Filter by **exact type**, verify **exact counts**, and inspect **payloads and forbidden-event branches**. For synchronous events, this approach is very stable. For async, transactions, or broker delivery, add matching test mechanisms because **recording an event does not mean consumers finished or data committed**.

## References

- [Spring Framework — Application Events in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — ApplicationEvents Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12-SNAPSHOT/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Java 17 — java.util.stream.Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
