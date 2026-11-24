# Testing Event Emission Counts in Spring Framework

## 1. Purpose: Counting Exactly What You Need to Verify

In an event-driven application, a valid command may need to emit exactly one domain event. Emitting too few leaves consumers out of sync; emitting too many can send duplicate notifications, double-charge fees, write duplicate audit entries, or enqueue extra work. Therefore, testing **event emission count** must be part of the business contract, not merely checking the event type.

Distinguish five metrics:

| Metric | How to Measure | Meaning |
| --- | --- | --- |
| **Publisher calls** | Mockito `verify(publisher, times(n))` | How many times the service layer called the publish API |
| **Event recordings** | Spring Test `ApplicationEvents.stream(EventType.class).count()` | How many events/payloads of that type were recorded in the test |
| **Listener calls** | Spy, counter, or mock listener | How many times a specific listener was invoked |
| **After-commit handler calls** | Spy or inspecting side effects after a real commit | How many times a transaction-phase listener ran |
| **Broker delivery / consumer side effects** | Integration tests with broker, outbox, deduplication | How many messages/transactions were received and applied after retries |

**One publish does not mean one listener execution across the whole system.** One event can be received by three listeners. Conversely, an `@Async` listener may not have run yet when the publisher returns. An event emitted inside a transaction that later rolls back can still be counted by `ApplicationEvents`, while an `AFTER_COMMIT` listener never runs.

Simple diagram:

```text
SubmitOrder("O-100")
    |
    v
Application service
    |
    +-- validate domain
    +-- repository/persistence boundary
    +-- publishEvent(OrderSubmitted)  <-- publisher calls: 1
             |
             +-- Listener A            <-- listener A calls: 1
             +-- Listener B            <-- listener B calls: 1

Total listener calls = 2, yet event emission count = 1.
```

## 2. Write the Count Contract Before Writing Tests

| Scenario | `OrderSubmitted` Count to Publish | Interpretation |
| --- | ---: | --- |
| One valid command | 1 | One business fact accepted |
| Input violating invariant | 0 | No success event |
| Two independent valid commands | 2 | Each command creates one event |
| One command traversing multiple helper methods | Usually 1 | Do not duplicate publishing across layers |
| Same idempotency key retried | Design-dependent, usually no new fact | Requires key storage state and clear policy |
| Transaction rolls back after calling publisher | May have called 1 | Publish count is not committed count |
| One event reaching two listeners | 1 publisher call, two listener calls | Counts must not sum handler invocations |

The counting unit must be clear: per command, per aggregate, per transaction, per test window, or per batch. A domain operation sometimes emits **multiple valid event types**; do not force every problem into the number 1.

## 3. Unit Testing: Mockito verify(times(n)) and ArgumentCaptor

If you want to verify directly that a service calls `ApplicationEventPublisher.publishEvent(...)` the exact number of times, testing with a mocked publisher is the least expensive approach. No Spring context is required.

```java
ApplicationEventPublisher publisher = mock(ApplicationEventPublisher.class);
SubmissionService service = new SubmissionService(publisher);

service.submit("O-10", 1200);

ArgumentCaptor<OrderSubmitted> captor =
        ArgumentCaptor.forClass(OrderSubmitted.class);
verify(publisher, times(1)).publishEvent(captor.capture());
assertEquals("O-10", captor.getValue().orderId());
verifyNoMoreInteractions(publisher);
```

This is an **excerpt**; the complete project with classes and imports is in section 5. `ArgumentCaptor` verifies the payload, not just the type. `verifyNoMoreInteractions` catches any additional publisher calls that the test did not assert.

Rejection branch:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.submit("O-10", 0));
verifyNoInteractions(publisher);
```

Testing zero emissions catches regressions where code emits a success event *before* validating input.

Note that `ApplicationEventPublisher` has two overloads: `publishEvent(ApplicationEvent)` and `publishEvent(Object)`. For a domain event that is a Java record not extending `ApplicationEvent`, `publishEvent(record)` picks the `Object` overload. In tests, use a captor with the exact event type so Mockito matches accurately.

**Mockito limitation:** mocking verifies the service's invocation; it does not prove Spring dispatched the event, listeners were registered properly, transactions committed, or brokers received messages.

## 4. Spring TestContext: @RecordApplicationEvents

Spring Framework supports recording application events during the execution of **a single test method**. Usage:

1. Place `@RecordApplicationEvents` on the test class.
2. Use `@SpringJUnitConfig` or `SpringExtension` with equivalent configuration.
3. Receive `ApplicationEvents` via a `@Test` parameter.
4. Execute the behavior under test and count `events.stream(OrderSubmitted.class).count()`.

```java
@Test
void publishesOne(@Autowired SubmissionService service,
                  ApplicationEvents events) {
    events.clear();
    service.submit("O-10", 1200);
    assertEquals(1L, events.stream(OrderSubmitted.class).count());
}
```

The snippet above is illustrative only, using classes/imports from the complete example below.

`ApplicationEvents.stream(Class<T>)` filters both `ApplicationEvent`s and **payload objects** of that type. This matters because when `publishEvent(Object)` receives a POJO, Spring may wrap it in `PayloadApplicationEvent`, yet you can still query the stream by the original payload type.

`ApplicationEvents.clear()` starts a fresh observation window. It clears only **the test recorder's event records**; it does not delete sent events, undo listeners, or roll back transactions.

The recorder is scoped per test method, so declaring a method parameter is better than holding the object long-term. If the context emits framework events like `ContextRefreshedEvent`, filter by the concrete type rather than calling `events.stream().count()` and assuming every event is a business event.

## 5. Complete Runnable Maven + Java 17 Example

The project uses Spring Framework 6.2.8, JUnit Jupiter 5.12.2, and Mockito 5.18.0. One service executes commands, and one synchronous listener counts received events. There are 3 unit tests and 3 integration tests.

### 5.1. Structure

```text
spring-event-count-test/
├── pom.xml
├── src/main/java/demo/EventCountApp.java
├── src/test/java/demo/EventPublicationUnitTest.java
└── src/test/java/demo/EventPublicationIntegrationTest.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-count-test</artifactId>
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
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.18.0</version>
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
```

### 5.3. src/main/java/demo/EventCountApp.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventCountApp {

    public record OrderSubmitted(String orderId, long amountInCents) {}

    public static final class SubmissionService {
        private final ApplicationEventPublisher publisher;

        public SubmissionService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId, long amountInCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId required");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            publisher.publishEvent(
                    new OrderSubmitted(orderId, amountInCents));
        }
    }

    public static final class CountingListener {
        private final AtomicInteger counter = new AtomicInteger();

        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            counter.incrementAndGet();
        }

        public int calls() {
            return counter.get();
        }

        public void reset() {
            counter.set(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SubmissionService submissionService(
                ApplicationEventPublisher publisher) {
            return new SubmissionService(publisher);
        }

        @Bean
        CountingListener countingListener() {
            return new CountingListener();
        }
    }
}
```

### 5.4. src/test/java/demo/EventPublicationUnitTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class EventPublicationUnitTest {

    @Test
    void oneValidCommandPublishesOneEventWithCorrectPayload() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        service.submit("O-10", 1200);

        ArgumentCaptor<EventCountApp.OrderSubmitted> captor =
                ArgumentCaptor.forClass(
                        EventCountApp.OrderSubmitted.class);
        verify(publisher, times(1)).publishEvent(captor.capture());

        assertEquals("O-10", captor.getValue().orderId());
        assertEquals(1200L, captor.getValue().amountInCents());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidCommandPublishesNothing() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        assertThrows(IllegalArgumentException.class,
                () -> service.submit("O-11", 0));
        verifyNoInteractions(publisher);
    }

    @Test
    void twoCommandsPublishTwoEvents() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        service.submit("O-20", 100);
        service.submit("O-21", 200);

        verify(publisher, times(2)).publishEvent(
                any(EventCountApp.OrderSubmitted.class));
        verifyNoMoreInteractions(publisher);
    }
}
```

### 5.5. src/test/java/demo/EventPublicationIntegrationTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = EventCountApp.Config.class)
@RecordApplicationEvents
class EventPublicationIntegrationTest {

    @Test
    void oneCommandRecordedOnceAndListenerRunsOnce(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        service.submit("O-10", 1200);

        assertEquals(1L,
                events.stream(EventCountApp.OrderSubmitted.class).count());
        assertEquals("O-10",
                events.stream(EventCountApp.OrderSubmitted.class)
                        .findFirst().orElseThrow().orderId());
        assertEquals(1, listener.calls());
    }

    @Test
    void invalidCommandRecordsZeroEvents(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        assertThrows(IllegalArgumentException.class,
                () -> service.submit("O-11", -10));

        assertEquals(0L,
                events.stream(EventCountApp.OrderSubmitted.class).count());
        assertEquals(0, listener.calls());
    }

    @Test
    void twoCommandsRecordedExactlyTwice(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        service.submit("O-20", 100);
        service.submit("O-21", 200);

        List<String> ids =
                events.stream(EventCountApp.OrderSubmitted.class)
                        .map(EventCountApp.OrderSubmitted::orderId)
                        .toList();

        assertEquals(List.of("O-20", "O-21"), ids);
        assertEquals(2, listener.calls());
    }
}
```

### 5.6. Running and Reading Results

In the directory containing `pom.xml`, JDK 17+ and Maven are required:

```bash
mvn -q clean test
```

The project has **two test classes and six test methods**. When assertions pass, Maven returns **exit code 0**. Maven logs/stdout can differ by configuration, so do not fabricate a fixed output block. Omit `-q` to inspect Surefire's actual summary.

| Test | Publisher calls | Recorder events | Listener invocations |
| --- | ---: | ---: | ---: |
| Unit: 1 valid command | 1 | Not used | Not used |
| Unit: 1 invalid command | 0 | Not used | Not used |
| Unit: 2 valid commands | 2 | Not used | Not used |
| Integration: 1 valid command | 1 per service logic | 1 | 1 |
| Integration: 1 invalid command | 0 per service logic | 0 | 0 |
| Integration: 2 valid commands | 2 per service logic | 2 | 2 |

`CountingListener` in the demo runs **synchronously by default**, so you can assert invocation counts immediately after `submit(...)`. If replaced with `@Async`, immediate assertions become unreliable.

## 6. Counting by Type Is Not Enough: Check Payload and Scope

A publish call may have the right count yet the wrong order ID. Therefore, unit tests use `ArgumentCaptor`; in integration tests, `events.stream(...).map(OrderSubmitted::orderId)` confirms IDs.

You can filter for a specific order:

```java
long countForOrder = events.stream(EventCountApp.OrderSubmitted.class)
        .filter(event -> event.orderId().equals("O-10"))
        .count();
assertEquals(1L, countForOrder);
```

This excerpt requires an `events` variable in the test. With multiple tenants or aggregates, distinguish by the appropriate context/ID. An `@EventListener(condition = "...")` may skip events, making listener invocations fewer than publisher calls without necessarily being a bug.

With parent/child `ApplicationContext`s, events can propagate to the parent; explicitly specify which context and event types are in measurement scope. With multiple listeners for the same type, total listener calls can exceed publish counts.

## 7. Transactions: Event Count Does Not Prove Commit

Inside a transaction:

```text
BEGIN
  update orders
  publishEvent(OrderSubmitted) <-- recorder may count 1
  ...
ROLLBACK                         <-- DB record lost
                                 <-- AFTER_COMMIT handler does not run
```

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` triggers only after a successful commit of the matching transaction. The `ApplicationEvents` recorder tracks **published events**, not a list of durably persisted "committed domain facts."

To test post-commit processing:

1. Use a real transaction manager/DB in integration tests.
2. Publish inside a transaction, then commit or roll back in a controlled manner.
3. Verify publisher call counts, recorded events, and after-commit callback executions separately.
4. Note that many Spring `@Transactional` tests auto-roll back after the test; asserting before commit misses the after-commit phase by design.
5. Do not infer "no event" just because `AFTER_COMMIT` did not run after rollback; the event may have been published.

By default, `@TransactionalEventListener` does not run when an event is published outside a transaction unless `fallbackExecution=true` is configured. With `AFTER_ROLLBACK`, the matching-phase callback can run even though after-commit did not.

## 8. Async: Testing Listener Counts Must Not Rely on Sleep

With `@Async` or an executor on the multicaster, the publisher may return before the listener executes. An immediate assertion:

```java
publisher.publishEvent(new OrderSubmitted("O-10", 100));
assertEquals(1, listener.calls()); // Can be flaky if async.
```

is unstable. Use a `CountDownLatch` or future/completion with a bounded timeout, not `Thread.sleep(1000)` as a primary strategy.

```java
// Conceptual snippet; requires appropriate listener and imports.
CountDownLatch completed = new CountDownLatch(1);
// Listener calls completed.countDown() when finished processing.
assertTrue(completed.await(3, TimeUnit.SECONDS));
assertEquals(1, processedCounter.get());
```

Each test must measure the right milestone: task enqueued, listener started, or processing completed. With `ApplicationEvents`, the recorder belongs to the test method lifecycle; publishing from a separate thread pool can involve different context/test-recorder propagation mechanisms. Do not assume every event emitted on any executor appears identically.

When using async, also test error-handling channels. A listener running twice due to worker retries does not prove the publisher called twice.

## 9. Brokers, Outbox, and Delivery Counts

`verify(publisher, times(1))` does **not** prove "exactly once" when brokers and networks are involved.

Transactional outbox example:

```text
TX: insert outbox(eventId=E-1) -> COMMIT
relay attempt 1: broker accepted E-1
relay crashes before marking delivered
relay attempt 2: broker accepted E-1 again
consumer may see E-1 twice
```

One business fact has exactly one outbox row, yet the broker may receive multiple copies after retries. Verify:

- Stable `eventId`, unique constraint, or idempotency key for the fact.
- State and outbox row commit/roll back atomically in the same transaction.
- Relay can retry after a crash without losing events.
- Consumer receives the same event ID multiple times yet applies side effects per idempotent policy.
- When per-aggregate ordering exists, test ordering and replay per contract; do not treat count as proof of ordering preservation.

Do not conflate the number of domain events created, publisher calls, broker sends, consumer receives, and successful side effects.

## 10. Avoiding Flaky Tests and Noisy State

**ApplicationContext caching:** Spring TestContext can cache contexts across tests. The demo's `CountingListener` is a singleton; hence tests called `listener.reset()` before measuring. Without resetting, later tests can observe counts accumulated from prior tests.

**Recorder scope:** `ApplicationEvents` is per test method; do not store it in static fields or inject it into test constructors. Use method parameters; call `events.clear()` when you want a clean window.

**Framework events:** `ContextRefreshedEvent` and test lifecycle events may appear alongside yours. Filter by event type and payload instead of counting all events.

**Mock interactions:** use `verifyNoInteractions(publisher)` for branches expecting zero publisher calls; use `verifyNoMoreInteractions` after verifying expected calls to catch extra events.

**Parallelism:** if enabling parallel tests with a mutable singleton listener, resets can collide. Use per-test instances/scopes, appropriate counters, or context/resource isolation; do not assume the synchronous demo is safe under parallel execution.

**Listener exceptions:** a synchronous listener throwing an exception can make `publishEvent` exit abnormally after some listeners have already run. Publisher calls, recorded events, and listener calls can diverge. Test root causes and rollback/error-handler policies separately.

## 11. Choosing the Right Test Level

| Level | Tools | Reliable Conclusion |
| --- | --- | --- |
| Service unit | Mockito `times(n)`, captor | Code calls publisher `n` times with the right payload |
| Spring integration | `@RecordApplicationEvents`, `ApplicationEvents` | Context records events/payloads of the right type and count |
| Listener integration | Spy/counter and sync controls | Specific listener executes the exact number of times |
| Transaction integration | DB + transaction manager | Distinguishes before/after commit and rollback |
| Broker/outbox integration | Testcontainers/real broker, relay, deduplication | Tests bounded delivery/retry/idempotency |

In production systems, add low-cardinality metrics per event type to detect abnormal publish counts. However, metrics do not replace test assertions, and you must never assume one event equals one span or one successfully delivered message.

## 12. Pre-Completion Checklist

- [ ] Clearly state how many events must be emitted per command/batch.
- [ ] Cover **0**, **1**, and **2/n** event cases.
- [ ] Verify event type **and** payload; not count alone.
- [ ] Unit test publisher via `verify(times(n))`/`ArgumentCaptor`.
- [ ] Spring integration via `@RecordApplicationEvents`/`ApplicationEvents.stream(type)`.
- [ ] Filter framework/lifecycle events out of domain event counts.
- [ ] Reset listener state or isolate test contexts when needed.
- [ ] Do not confuse publisher invocation counts with listener invocation counts.
- [ ] Do not treat publishing prior to rollback as after-commit success.
- [ ] For async, use synchronization and bounded timeouts.
- [ ] For outbox/broker, test retries, duplicates, and idempotent consumers.
- [ ] Do not claim "exactly once" for side effects based on a single assertion.

## 13. Self-Check Questions

1. **If one event has three listeners, how many publisher calls occur?** — Possibly just one, depending on emitting code.
2. **Which tool counts publisher calls in unit tests?** — Mockito `verify(..., times(n))`.
3. **How do you verify the emitted payload is accurate?** — `ArgumentCaptor` or reading payloads from the `ApplicationEvents` stream.
4. **What counts events in Spring TestContext?** — `@RecordApplicationEvents` and `ApplicationEvents.stream(EventType.class).count()`.
5. **Why is `events.clear()` needed?** — Sets a clean counting baseline in the test without deleting real publications.
6. **Can an event published and then rolled back still be counted by the recorder?** — Yes.
7. **Does an `AFTER_COMMIT` listener run after rollback?** — No.
8. **Why can asserting listener count immediately fail under `@Async`?** — The worker may not have finished processing yet.
9. **Does Mockito verifying once guarantee a broker will not deliver duplicates?** — No.
10. **Why reset a singleton listener before each test?** — Context caching can retain counters across test methods.

## References

- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — ApplicationEvents API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Mockito Documentation](https://site.mockito.org/)
